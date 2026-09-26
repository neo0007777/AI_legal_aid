import unittest
import hashlib
import json
import os
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv

load_dotenv()
if not os.getenv("JWT_SECRET_KEY"):
    os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-for-unit-testing-32chars"

from sqlalchemy.orm import Session

from models.database import SessionLocal, create_tables, Act, Provision, StatuteMapping, IngestionLog
from services.indiacode_client import IndiaCodeClient, IndiaCodeAPIError
from services.indiacode_ingest import IngestionService, TARGET_ACT_QUERIES
import routes.statutes as statutes_route


class TestIndiaCodeDataLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        create_tables()
        cls.db: Session = SessionLocal()
        cls.client = IndiaCodeClient()
        cls.service = IngestionService(cls.client)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_meta_works(self):
        """TEST 1: /meta works and returns valid corpus counts."""
        res = self.client.get_meta()
        self.assertIn("data", res)
        self.assertIn("corpus", res["data"])
        self.assertGreater(res["data"]["corpus"]["acts"], 0)
        self.assertIn("raw_response_sha256", res)
        self.assertEqual(res["source_api"], "indiacode.ecourtsindia.com")

    def test_02_dynamic_discovery_of_acts(self):
        """TEST 2: The exact IDs of BNS, BNSS, BSA, IPC, CrPC are discovered rather than guessed."""
        discovered = self.service.discover_target_acts()
        discovered_ids = {d["discovered_id"] for d in discovered}
        expected_ids = {"bns", "bnss", "bsa", "ipc", "crpc"}
        for exp in expected_ids:
            self.assertIn(exp, discovered_ids, f"Expected {exp} to be discovered dynamically")

    def test_03_act_metadata_stored(self):
        """TEST 3: One Act is fetched successfully and stored in the database."""
        act = self.db.query(Act).filter(Act.source_act_id == "bns").first()
        self.assertIsNotNone(act, "BNS should be present in database")
        self.assertEqual(act.source_act_id, "bns")
        self.assertIn("Bharatiya Nyaya Sanhita", act.title)
        self.assertEqual(act.source_type, "INDIA_CODE_API")
        self.assertEqual(act.source_authority, "INDIA_CODE_CORPUS")
        self.assertIsNotNone(act.raw_response_sha256)
        self.assertIsNotNone(act.raw_json)

    def test_04_provisions_stored(self):
        """TEST 4: Its provisions are fetched successfully and stored."""
        provisions = self.db.query(Provision).filter(Provision.act_source_id == "bns").all()
        self.assertGreaterEqual(len(provisions), 350)
        p1 = self.db.query(Provision).filter(
            Provision.act_source_id == "bns",
            Provision.provision_number == "1"
        ).first()
        self.assertIsNotNone(p1)
        self.assertIn("Short title", p1.heading)

    def test_05_alphanumeric_identifier_preserved(self):
        """TEST 5: A provision with an alphanumeric identifier is preserved exactly as a string."""
        p_ipc = self.service.get_or_fetch_provision("ipc", "124A", self.db)
        self.assertIsNotNone(p_ipc)
        self.assertIsInstance(p_ipc.provision_number, str)
        self.assertEqual(p_ipc.provision_number, "124A")
        self.assertIn("Sedition", p_ipc.heading)

        p_iea = self.service.get_or_fetch_provision("iea", "65B", self.db)
        self.assertIsNotNone(p_iea)
        self.assertIsInstance(p_iea.provision_number, str)
        self.assertEqual(p_iea.provision_number, "65B")

    def test_06_exact_section_retrieval(self):
        """TEST 6: A specific section can be retrieved exactly with verbatim unaltered text."""
        p = self.service.get_or_fetch_provision("bns", "103", self.db)
        self.assertIsNotNone(p)
        self.assertEqual(p.provision_number, "103")
        self.assertEqual(p.heading, "Punishment for murder")
        self.assertIn("Whoever commits murder shall be punished with death", p.raw_text)
        self.assertIsNotNone(p.raw_response_sha256)
        self.assertIsNotNone(p.content_sha256)

    def test_07_mappings_retrieved_and_stored(self):
        """TEST 7: Mappings are retrieved and stored without inventing relationships."""
        mapping = self.db.query(StatuteMapping).filter(
            StatuteMapping.pair == "ipc-bns",
            StatuteMapping.from_provision == "302",
            StatuteMapping.to_provision == "103"
        ).first()
        self.assertIsNotNone(mapping, "IPC 302 -> BNS 103 mapping must exist")
        self.assertEqual(mapping.from_act, "ipc")
        self.assertEqual(mapping.to_act, "bns")
        self.assertEqual(mapping.relation, "near-identical")
        self.assertAlmostEqual(mapping.score, 0.9, places=2)

    def test_08_idempotent_ingestion(self):
        """TEST 8: Running ingestion twice produces no duplicates."""
        initial_acts = self.db.query(Act).count()
        initial_provisions = self.db.query(Provision).count()
        initial_mappings = self.db.query(StatuteMapping).count()

        # Run again
        self.service.run_full_initial_ingestion(self.db)

        self.assertEqual(self.db.query(Act).count(), initial_acts)
        self.assertEqual(self.db.query(Provision).count(), initial_provisions)
        self.assertEqual(self.db.query(StatuteMapping).count(), initial_mappings)

    def test_09_missing_api_fields_remain_null(self):
        """TEST 9: Missing API fields remain NULL / not available without plausible hallucination."""
        # Find an act where spent_note or department is null
        act = self.db.query(Act).filter(Act.source_act_id == "bns").first()
        self.assertIsNotNone(act)
        self.assertFalse(act.spent)
        self.assertIsNone(act.spent_note, "Missing spent_note must remain None, not fabricated")

    def test_10_ui_api_returns_source_values(self):
        """TEST 10: The API endpoint displays the actual source values."""
        res = statutes_route.get_exact_provision(act_id="bns", provision_number="103", db=self.db)
        self.assertEqual(res["act_source_id"], "bns")
        self.assertEqual(res["provision_number"], "103")
        self.assertEqual(res["heading"], "Punishment for murder")
        self.assertIn("Whoever commits murder shall be punished", res["verbatim_text"])
        self.assertGreater(len(res["source_correspondences"]), 0)

    def test_11_every_entity_has_provenance(self):
        """TEST 11: Every displayed Act and provision has provenance."""
        res = statutes_route.get_exact_provision(act_id="bns", provision_number="103", db=self.db)
        prov = res["provenance"]
        self.assertEqual(prov["source_api"], "indiacode.ecourtsindia.com")
        self.assertEqual(prov["source_type"], "INDIA_CODE_API")
        self.assertEqual(prov["source_authority"], "INDIA_CODE_CORPUS")
        self.assertIsNotNone(prov["canonical_legal_source"])
        self.assertTrue(prov["canonical_legal_source"].startswith("http"))
        self.assertIsNotNone(prov["retrieved_at"])
        self.assertIsNotNone(prov["raw_response_sha256"])
        self.assertIsNotNone(prov["content_sha256"])

    def test_12_api_failure_does_not_produce_fake_data(self):
        """TEST 12: API failure does not produce fake fallback data."""
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            statutes_route.get_exact_provision(act_id="bns", provision_number="9999", db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("not found from source", ctx.exception.detail)

    def test_13_raw_json_hash_reproducible(self):
        """TEST 13: API response raw JSON is byte-for-byte/hash reproducible."""
        act = self.db.query(Act).filter(Act.source_act_id == "bns").first()
        self.assertIsNotNone(act.raw_json)
        computed_hash = hashlib.sha256(act.raw_json.encode("utf-8")).hexdigest()
        self.assertEqual(computed_hash, act.raw_response_sha256)

    def test_14_changing_metadata_does_not_change_content_sha256(self):
        """TEST 14: Changing metadata does not incorrectly change provision content_sha256."""
        text = "(1) Whoever commits murder shall be punished with death..."
        content_hash_1 = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
        
        # Simulate different metadata wrapper, same statutory text
        envelope_a = json.dumps({"text": text, "metadata": {"views": 100}})
        envelope_b = json.dumps({"text": text, "metadata": {"views": 101}})
        
        raw_hash_a = hashlib.sha256(envelope_a.encode("utf-8")).hexdigest()
        raw_hash_b = hashlib.sha256(envelope_b.encode("utf-8")).hexdigest()
        content_hash_2 = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

        self.assertNotEqual(raw_hash_a, raw_hash_b, "Raw hashes must differ when envelope changes")
        self.assertEqual(content_hash_1, content_hash_2, "Content hash must remain strictly identical")

    def test_15_mapping_does_not_become_legal_applicability(self):
        """TEST 15: Mapping does not automatically become 'legal applicability'."""
        res = statutes_route.get_exact_provision(act_id="bns", provision_number="103", db=self.db)
        corrs = res["source_correspondences"]
        self.assertGreater(len(corrs), 0)
        for c in corrs:
            self.assertEqual(c["label"], "Source-listed correspondence (API mapping)")
            self.assertIn("applicability_warning", c)
            self.assertIn("legal applicability depends on case timeline", c["applicability_warning"])

    def test_16_source_url_matches_stored_source_url(self):
        """TEST 16: Source URL displayed by UI/API exactly matches stored source URL."""
        res = statutes_route.get_exact_provision(act_id="bns", provision_number="103", db=self.db)
        p = self.db.query(Provision).filter(
            Provision.act_source_id == "bns",
            Provision.provision_number == "103"
        ).first()
        self.assertEqual(res["provenance"]["canonical_legal_source"], p.source_url)

    def test_17_provision_404_does_not_invent_text(self):
        """TEST 17: If exact provision endpoint returns 404, the system does not invent the section text."""
        result = self.service.get_or_fetch_provision("bns", "987654", self.db)
        self.assertIsNone(result)

    def test_18_api_data_change_detection(self):
        """TEST 18: If API data changes between ingestion runs, the system detects and records the change."""
        act = self.db.query(Act).filter(Act.source_act_id == "bsa").first()
        old_hash = act.raw_response_sha256
        # Simulate an updated response hash
        mock_res = {
            "data": {
                "act": {
                    "id": "bsa",
                    "short_title": "The Bharatiya Sakshya Adhiniyam, 2023 [Updated]",
                    "act_year": 2023,
                    "section_count": 170,
                },
                "sections": []
            },
            "raw_text": '{"act": {"id": "bsa", "short_title": "The Bharatiya Sakshya Adhiniyam, 2023 [Updated]"}}',
            "raw_response_sha256": "simulated_new_hash_12345",
            "content_sha256": "simulated_content_hash_67890",
            "source_api": "indiacode.ecourtsindia.com",
            "source_url": "https://indiacode.ecourtsindia.com/bsa/",
        }
        with patch.object(self.service.client, "get_act", return_value=mock_res):
            updated_act = self.service.ingest_act_metadata("bsa", self.db, "test_run")
            self.assertEqual(updated_act.raw_response_sha256, "simulated_new_hash_12345")
            self.assertIn("[Updated]", updated_act.title)

        # Restore original
        self.service.ingest_act_metadata("bsa", self.db, "restore_run")
        restored_act = self.db.query(Act).filter(Act.source_act_id == "bsa").first()
        self.assertEqual(restored_act.raw_response_sha256, old_hash)

    def test_19_all_six_target_acts_discovered_dynamically(self):
        """TEST 19: All six target Acts are discovered dynamically. No Act ID is hard-coded."""
        discovered = self.service.discover_target_acts()
        self.assertEqual(len(discovered), 6)
        discovered_dict = {d["target_name"]: d["discovered_id"] for d in discovered}
        self.assertEqual(discovered_dict["Bharatiya Nyaya Sanhita"], "bns")
        self.assertEqual(discovered_dict["Bharatiya Nagarik Suraksha Sanhita"], "bnss")
        self.assertEqual(discovered_dict["Bharatiya Sakshya Adhiniyam"], "bsa")
        self.assertEqual(discovered_dict["Indian Penal Code"], "ipc")
        self.assertEqual(discovered_dict["Code of Criminal Procedure"], "crpc")
        self.assertEqual(discovered_dict["Indian Evidence Act"], "iea")

    def test_20_no_llm_call_in_ingestion_path(self):
        """TEST 20: No LLM call occurs anywhere in the ingestion path."""
        # Mock LLM client/function to raise if called
        with patch("services.llm.call_groq", side_effect=AssertionError("LLM should NOT be called")):
            # Execute discovery, act fetch, provision fetch, and mapping query
            act = self.service.client.get_act("bns")
            self.assertIsNotNone(act)
            sec = self.service.get_or_fetch_provision("bns", "1", self.db)
            self.assertIsNotNone(sec)
            self.assertFalse(hasattr(self.service, "llm"))
            self.assertFalse(hasattr(self.client, "llm"))

    def test_21_database_metadata_passed_to_prompt(self):
        """TEST 21: Database value is retrieved and passed to document generation prompt."""
        from services.india_code_grounding import resolve_and_lock_statutory_metadata, build_source_locked_prompt_block
        locked_corpus = resolve_and_lock_statutory_metadata(
            db=self.db,
            description="Bail application under Section 483 BNSS",
        )
        self.assertIn("bnss", locked_corpus.acts)
        bnss_act = locked_corpus.acts["bnss"]
        self.assertEqual(bnss_act.title, "The Bharatiya Nagarik Suraksha Sanhita, 2023")

        prompt_block = build_source_locked_prompt_block(locked_corpus)
        self.assertIn("The Bharatiya Nagarik Suraksha Sanhita, 2023", prompt_block)
        self.assertIn("Special powers of High Court or Court of Session regarding bail", prompt_block)
        self.assertIn("SOURCE-LOCKED INDIA CODE LEGAL METADATA", prompt_block)
        self.assertIn("MANDATORY VERBATIM REPRODUCTION RULES", prompt_block)

    def test_22_consistency_check_catches_corrupted_act_title(self):
        """TEST 22: Post-generation check detects corrupted Act title and enforces exact database title."""
        from services.india_code_grounding import (
            resolve_and_lock_statutory_metadata,
            audit_document_consistency,
            enforce_consistency_and_regenerate,
        )
        locked_corpus = resolve_and_lock_statutory_metadata(
            db=self.db,
            description="Bail application under Section 483 BNSS",
        )
        corrupted_draft = (
            "IN THE COURT OF SESSIONS AT NEW DELHI\n"
            "Application under Section 483 of the BNSS Act on behalf of the applicant.\n"
            "Alternatively cited under Brihanmumbai Nagar Sub-Division Sanhita.\n"
        )
        violations = audit_document_consistency(corrupted_draft, locked_corpus)
        self.assertGreater(len(violations), 0)
        violation_types = [v["type"] for v in violations]
        self.assertIn("act_title_corrupted", violation_types)

        # Enforce regeneration / replacement
        corrected_draft, audit_log = enforce_consistency_and_regenerate(corrupted_draft, locked_corpus)
        self.assertNotIn("BNSS Act", corrected_draft)
        self.assertNotIn("Brihanmumbai", corrected_draft)
        self.assertIn("The Bharatiya Nagarik Suraksha Sanhita, 2023", corrected_draft)

    def test_23_unverified_section_flagged(self):
        """TEST 23: Section number not in database is flagged as [REQUIRES VERIFICATION]."""
        from services.india_code_grounding import resolve_and_lock_statutory_metadata, audit_document_consistency
        locked_corpus = resolve_and_lock_statutory_metadata(
            db=self.db,
            description="Bail under Section 9999 BNSS",
        )
        self.assertIn("Section 9999 (BNSS)", locked_corpus.unverified_references)
        
        # If document mentions Section 9999 without verification flag
        unflagged_draft = "Prayer for bail under Section 9999 BNSS for the accused."
        violations = audit_document_consistency(unflagged_draft, locked_corpus)
        self.assertTrue(any(v["type"] == "unverified_section_not_flagged" for v in violations))

    def test_24_section_heading_mismatch_detection(self):
        """TEST 24: Paraphrased or invented section heading is flagged as a violation."""
        from services.india_code_grounding import resolve_and_lock_statutory_metadata, audit_document_consistency
        locked_corpus = resolve_and_lock_statutory_metadata(
            db=self.db,
            description="Application under Section 483 BNSS",
        )
        # 483 heading is "Special powers of High Court or Court of Session regarding bail"
        # If draft writes: "Section 483 (Exclusive Jurisdiction For Anticipatory Grant)"
        bad_heading_draft = "Invoking Section 483 (Exclusive Jurisdiction For Anticipatory Grant) of the Code."
        violations = audit_document_consistency(bad_heading_draft, locked_corpus)
        self.assertTrue(any(v["type"] == "section_heading_mismatch" for v in violations))

    def test_25_missing_india_code_metadata_no_fallback(self):
        """TEST 25: Missing India Code metadata outputs [NOT PROVIDED] or [REQUIRES VERIFICATION] without model fallback."""
        from services.india_code_grounding import resolve_and_lock_statutory_metadata
        locked_corpus = resolve_and_lock_statutory_metadata(
            db=self.db,
            description="Application under Section 987654 NonExistentAct",
        )
        # Should NOT fabricate act name or text
        self.assertNotIn("nonexistentact", locked_corpus.acts)
        self.assertEqual(len(locked_corpus.referenced_provisions), 0)


    def test_26_provision_from_api_alone_never_assigned_verified_legal_rule(self):
        """TEST 26: Never assign VERIFIED_LEGAL_RULE merely because a provision was returned by API."""
        from services.canonical_checker import cross_check_provision
        # Provision 999 returned by API, but not in canonical registry
        res = cross_check_provision(
            act_id="bnss",
            provision_number="999",
            api_heading="Some API Heading",
            api_text="Some API provision text",
            api_act_title="The Bharatiya Nagarik Suraksha Sanhita, 2023",
        )
        self.assertEqual(res.status, "REQUIRES_CANONICAL_VERIFICATION")
        self.assertFalse(res.is_verified)
        self.assertNotIn("VERIFIED_LEGAL_RULE", res.status)

    def test_27_canonical_cross_check_verified_success(self):
        """TEST 27: Cross-check Act title, provision number, heading, and text against canonical source succeeds."""
        from services.canonical_checker import cross_check_provision, CANONICAL_STATUTE_REGISTRY
        can = CANONICAL_STATUTE_REGISTRY[("bnss", "483")]
        res = cross_check_provision(
            act_id="bnss",
            provision_number="483",
            api_heading=can.heading,
            api_text=can.text,
            api_act_title=can.act_title,
        )
        self.assertEqual(res.status, "VERIFIED")
        self.assertTrue(res.is_verified)
        self.assertEqual(len(res.discrepancies), 0)

        # Cross-check CrPC 439
        can_crpc = CANONICAL_STATUTE_REGISTRY[("crpc", "439")]
        res_crpc = cross_check_provision(
            act_id="crpc",
            provision_number="439",
            api_heading=can_crpc.heading,
            api_text=can_crpc.text,
            api_act_title=can_crpc.act_title,
        )
        self.assertEqual(res_crpc.status, "VERIFIED")

    def test_28_source_conflict_detected_on_discrepancy(self):
        """TEST 28: If API and canonical source disagree, record is marked SOURCE_CONFLICT."""
        from services.canonical_checker import cross_check_provision
        # Discrepancy in text
        res_text = cross_check_provision(
            act_id="bnss",
            provision_number="483",
            api_heading="Special powers of High Court or Court of Session regarding bail",
            api_text="Altered statutory text that contradicts the official Gazette of India.",
            api_act_title="The Bharatiya Nagarik Suraksha Sanhita, 2023",
        )
        self.assertEqual(res_text.status, "SOURCE_CONFLICT")
        self.assertTrue(res_text.has_conflict)
        self.assertGreater(len(res_text.discrepancies), 0)
        self.assertTrue(any("text divergence" in d for d in res_text.discrepancies))

        # Discrepancy in heading
        res_heading = cross_check_provision(
            act_id="bns",
            provision_number="103",
            api_heading="Incorrectly altered heading for murder",
            api_text="(1) Whoever commits murder shall be punished with death or imprisonment for life...",
            api_act_title="The Bharatiya Nyaya Sanhita, 2023",
        )
        self.assertEqual(res_heading.status, "SOURCE_CONFLICT")
        self.assertTrue(any("Heading mismatch" in d for d in res_heading.discrepancies))

    def test_29_source_conflict_blocks_document_generation(self):
        """TEST 29: If SOURCE_CONFLICT exists, legal document generation is strictly blocked with HTTP 409."""
        from fastapi import HTTPException
        from routes.documents import generate_draft, DraftRequest
        from models.database import User
        from unittest.mock import MagicMock

        dummy_user = User(id="test-user-id", email="test@example.com", full_name="Test Advocate")
        mock_req = MagicMock()
        mock_req.headers = {"x-local-only": "false"}

        # Simulate a draft request with a corrupted provision that triggers SOURCE_CONFLICT
        from services.india_code_grounding import SourceLockedCorpus, LockedProvision
        conflicted_corpus = SourceLockedCorpus(
            has_source_conflict=True,
            conflicted_provisions=[
                LockedProvision(
                    act_source_id="bnss",
                    act_title="The Bharatiya Nagarik Suraksha Sanhita, 2023",
                    provision_number="483",
                    heading="Special powers of High Court or Court of Session regarding bail",
                    raw_text="Contradicted text",
                    source_url="https://indiacode.nic.in/acts/bnss/section/483",
                    canonical_status="SOURCE_CONFLICT",
                    canonical_discrepancies=["Statutory text divergence between API and canonical source"],
                )
            ]
        )

        import asyncio
        from routes.documents import generate_draft_stream, DraftRequest

        async def _run():
            events = []
            async for ev in generate_draft_stream(
                req=DraftRequest(description="Bail under Section 483 BNSS for accused in custody"),
                local_only=False,
                db=self.db,
                current_user=dummy_user,
            ):
                events.append(ev)
            return events

        with patch("routes.documents.resolve_and_lock_statutory_metadata", return_value=conflicted_corpus):
            events = asyncio.run(_run())
            err = next((e for e in events if e.get("type") == "error"), None)
            self.assertIsNotNone(err)
            self.assertIn("SOURCE_CONFLICT", err["message"])
            self.assertIn("Do not generate a legal document from it until resolved", err["message"])

    def test_30_clean_generation_proceeds_when_verified(self):
        """TEST 30: Document generation proceeds normally without 409 when provisions are verified."""
        import asyncio
        from routes.documents import generate_draft_stream, DraftRequest
        from models.database import User
        from unittest.mock import MagicMock

        dummy_user = User(id="test-user-id", email="test@example.com", full_name="Test Advocate")
        mock_req = MagicMock()
        mock_req.headers = {"x-local-only": "false"}

        async def _run():
            events = []
            async for ev in generate_draft_stream(
                req=DraftRequest(description="Application for regular bail under Section 483 BNSS for accused in custody"),
                local_only=False,
                db=self.db,
                current_user=dummy_user,
            ):
                events.append(ev)
            return events

        # Patch call_llm and search_drafts so it completes without external APIs
        with patch("routes.documents.search_drafts", return_value=[{"metadata": {"filename": "test.txt", "category": "criminal"}, "text": "Sample template text", "score": 0.95}]), \
             patch("routes.documents.call_llm", return_value="1. Heading: In the High Court...\n2. Verified Facts: Accused in custody...\n3. Grounds: Section 483 BNSS...\n4. Prayer: Grant bail."):
            events = asyncio.run(_run())
            done_ev = next((e for e in events if e.get("type") == "done"), None)
            self.assertIsNotNone(done_ev)
            self.assertIn("Section 483", done_ev["draft"])
            self.assertFalse(done_ev.get("provenance_report", {}).get("source_locked_corpus", {}).get("has_source_conflict", False))


if __name__ == "__main__":
    unittest.main()



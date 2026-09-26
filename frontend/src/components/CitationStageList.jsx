import PipelineStageList from './PipelineStageList';

// Harness-sprint Part B: the actual named pipeline stages, in the order they
// really run. This mirrors backend/services/citation_verifier.py's emit()
// calls exactly -- if a stage genuinely runs, it's started/done; if
// correction memory short-circuits (or resolution fails), stages 2-4 are
// marked skipped with the real reason, never faked as instant.
const STAGE_ORDER = ['checking_correction_memory', 'resolving_citation', 'retrieving_judgment', 'running_entailment', 'applying_verdict'];

const STAGE_LABELS = {
    checking_correction_memory: 'Checking correction memory',
    resolving_citation: 'Resolving citation',
    retrieving_judgment: 'Retrieving judgment',
    running_entailment: 'Running entailment check',
    applying_verdict: 'Applying verdict',
};

const CitationStageList = ({ stages, caseName }) => (
    <PipelineStageList stages={stages} stageOrder={STAGE_ORDER} stageLabels={STAGE_LABELS} title={caseName} />
);

export default CitationStageList;

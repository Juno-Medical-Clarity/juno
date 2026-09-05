from __future__ import annotations
from .marker import CodeMarker, code_marker


class Markers:
    """Juno operation registry. Each leaf's name() is the emitted metric name."""

    class CarePlan:
        @code_marker("care_plan.read_input")
        class ReadInput(CodeMarker): pass

        @code_marker("care_plan.find_medical_terms")
        class FindMedicalTerms(CodeMarker): pass

        @code_marker("care_plan.simplify_language")
        class SimplifyLanguage(CodeMarker): pass

        @code_marker("care_plan.clarify_actions")
        class ClarifyActions(CodeMarker): pass

        @code_marker("care_plan.structure_note")
        class StructureNote(CodeMarker): pass

        @code_marker("care_plan.save_output")
        class SaveOutput(CodeMarker): pass

        @code_marker("care_plan.pipeline")
        class Pipeline(CodeMarker): pass

    class Grading:
        @code_marker("grading.run")
        class Run(CodeMarker): pass

        @code_marker("grading.route")
        class Route(CodeMarker): pass

    class Http:
        @code_marker("http.request")
        class Request(CodeMarker): pass

    class Athena:
        @code_marker("athena.get_token")
        class GetToken(CodeMarker): pass

        @code_marker("athena.fetch_encounter_summary")
        class FetchEncounterSummary(CodeMarker): pass

        @code_marker("athena.fetch_clinical_doc")
        class FetchClinicalDoc(CodeMarker): pass

        @code_marker("athena.api_call")
        class ApiCall(CodeMarker): pass

    class Batch:
        @code_marker("batch.create_jobs")
        class CreateJobs(CodeMarker): pass

        @code_marker("batch.create_single_job")
        class CreateSingleJob(CodeMarker): pass

    class Trial:
        @code_marker("trial.create_job")
        class CreateJob(CodeMarker): pass

        @code_marker("trial.delete_job")
        class DeleteJob(CodeMarker): pass

    class Worker:
        @code_marker("worker.job_execute")
        class JobExecute(CodeMarker): pass

        @code_marker("worker.job_stage")
        class JobStage(CodeMarker): pass

    class SavedOutputs:
        @code_marker("saved_outputs.list")
        class List(CodeMarker): pass

        @code_marker("saved_outputs.get")
        class Get(CodeMarker): pass

        @code_marker("saved_outputs.rename")
        class Rename(CodeMarker): pass

        @code_marker("saved_outputs.delete")
        class Delete(CodeMarker): pass

        @code_marker("saved_outputs.get_pdf_url")
        class GetPdfUrl(CodeMarker): pass

        @code_marker("saved_outputs.toggle_share")
        class ToggleShare(CodeMarker): pass

    class Firestore:
        @code_marker("firestore.job_write")
        class JobWrite(CodeMarker): pass

    class Retention:
        @code_marker("retention.anon_user_cleanup")
        class AnonUserCleanup(CodeMarker): pass

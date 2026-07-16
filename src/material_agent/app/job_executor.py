from contextlib import nullcontext


class JobExecutor:
    def __init__(self, review_job):
        self.review_job = review_job

    def run(self, job_id: str, file_paths: list[str]):
        batched_commits = getattr(self.review_job.repository, "batched_commits", None)
        transaction = batched_commits(commit_every=2048) if callable(batched_commits) else nullcontext()
        with transaction:
            return self.review_job.run(job_id, file_paths)

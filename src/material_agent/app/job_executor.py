class JobExecutor:
    def __init__(self, review_job):
        self.review_job = review_job

    def run(self, job_id: str, file_paths: list[str]):
        return self.review_job.run(job_id, file_paths)

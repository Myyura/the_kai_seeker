from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    app_name: str
    version: str = "0.1.0"
    project: str = "the-kai-seeker"
    homepage: str = "https://github.com/Myyura/the_kai_seeker"
    license: str = "AGPL-3.0"

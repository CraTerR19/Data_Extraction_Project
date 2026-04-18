from pydantic import BaseModel

class SubmitIdRequest(BaseModel):
    id: str

# Usually the update request would have its own BaseModel here optionally

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .deps import current_identity, store_of


router = APIRouter(prefix="/api/extension", tags=["extension"])


class PairCodeInput(BaseModel):
    code: str = Field(min_length=10, max_length=200)


@router.post("/pair")
def create_pair_code(request: Request) -> dict:
    identity = current_identity(request)
    return {
        "code": store_of(request).create_pair_code(identity.user_id),
        "expires_in": 300,
        "instructions": "在 ThinkSpace 浏览器扩展中粘贴此一次性配对码。",
    }


@router.post("/exchange")
def exchange_pair_code(payload: PairCodeInput, request: Request) -> dict:
    result = store_of(request).exchange_pair_code(payload.code)
    if not result:
        raise HTTPException(400, detail="配对码无效或已过期，请在网页端重新生成。")
    token, user_id = result
    return {"extension_token": token, "user_id": user_id, "token_type": "Bearer"}

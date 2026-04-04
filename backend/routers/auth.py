from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from ..database import get_supabase
from ..schemas import UserRegister, UserLogin, Token, UserResponse
from ..auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _with_onboarding_flag(user: dict, supabase: Client) -> dict:
    """Add onboarding_complete field to user dict."""
    result = (
        supabase.table("runner_assessments")
        .select("id")
        .eq("user_id", user["id"])
        .execute()
    )
    return {**user, "onboarding_complete": bool(result.data)}


@router.post("/register", response_model=Token)
def register(data: UserRegister, supabase: Client = Depends(get_supabase)):
    existing = supabase.table("users").select("id").eq("email", data.email).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Email already registered")

    result = supabase.table("users").insert({
        "email": data.email,
        "name": data.name,
        "password_hash": hash_password(data.password),
        "weight_kg": data.weight_kg,
        "max_hr": data.max_hr,
    }).execute()

    user = _with_onboarding_flag(result.data[0], supabase)
    token = create_access_token({"sub": user["id"]})
    return {"access_token": token, "token_type": "bearer", "user": UserResponse.model_validate(user)}


@router.post("/login", response_model=Token)
def login(data: UserLogin, supabase: Client = Depends(get_supabase)):
    result = supabase.table("users").select("*").eq("email", data.email).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_raw = result.data[0]
    if not verify_password(data.password, user_raw["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = _with_onboarding_flag(user_raw, supabase)
    token = create_access_token({"sub": user["id"]})
    return {"access_token": token, "token_type": "bearer", "user": UserResponse.model_validate(user)}


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    user = _with_onboarding_flag(current_user, supabase)
    return UserResponse.model_validate(user)

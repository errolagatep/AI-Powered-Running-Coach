from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from ..database import get_supabase
from ..schemas import AssessmentCreate, AssessmentResponse
from ..auth import get_current_user
from ..coach import get_onboarding_followup

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.post("/", response_model=AssessmentResponse)
def submit_assessment(
    data: AssessmentCreate,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    followup_q = get_onboarding_followup(data.model_dump())

    payload = {
        "user_id": current_user["id"],
        "experience_level": data.experience_level,
        "years_running": data.years_running,
        "weekly_runs": data.weekly_runs,
        "weekly_km": data.weekly_km,
        "primary_goal": data.primary_goal,
        "injury_history": data.injury_history,
        "available_days": data.available_days,
        "preferred_distance": data.preferred_distance,
        "load_capacity": data.load_capacity,
        "ai_followup_q": followup_q,
        "ai_followup_a": data.ai_followup_a,
    }

    # Upsert — user may redo onboarding
    existing = (
        supabase.table("runner_assessments")
        .select("id")
        .eq("user_id", current_user["id"])
        .execute()
    )
    if existing.data:
        result = (
            supabase.table("runner_assessments")
            .update({**payload, "updated_at": "now()"})
            .eq("user_id", current_user["id"])
            .execute()
        )
    else:
        result = supabase.table("runner_assessments").insert(payload).execute()

    return AssessmentResponse.model_validate(result.data[0])


@router.get("/", response_model=AssessmentResponse)
def get_assessment(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    result = (
        supabase.table("runner_assessments")
        .select("*")
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="No assessment found")
    return AssessmentResponse.model_validate(result.data[0])


@router.post("/answer", response_model=AssessmentResponse)
def save_followup_answer(
    body: dict,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    answer = body.get("answer", "")
    result = (
        supabase.table("runner_assessments")
        .update({"ai_followup_a": answer, "updated_at": "now()"})
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="No assessment found")
    return AssessmentResponse.model_validate(result.data[0])

from app.api.problems import ProblemException

def check_seat_cap(seats: int, current_invite_count: int, is_already_invited: bool) -> None:
    """
    Enforce seat cap.
    If the email is already invited, seat cap is not exceeded (it's an idempotent replay).
    If it's a new distinct invite and current_invite_count >= seats, return SEAT_CAP.
    """
    if not is_already_invited and current_invite_count >= seats:
        raise ProblemException(
            status=422,
            code="SEAT_CAP",
            title="Seat cap reached",
            detail=f"Cannot invite more admins: seat cap of {seats} reached",
        )

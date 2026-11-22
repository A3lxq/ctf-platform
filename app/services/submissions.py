"""Business logic for verifying and recording a flag submission.
Submission (full audit log) is always written; Solve (the authoritative
duplicate-guard + scoring source) is written only on a genuinely new
correct submission -- see models.py's own docstrings on why these are
two separate tables."""
import hmac

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import flags, models


class SubmissionServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def submit_flag(db: Session, team: models.Team, challenge: models.Challenge, value: str) -> bool:
    """Returns True if this submission is correct. Raises
    SubmissionServiceError(409, ...) up front if the team already
    solved this challenge -- a resubmit against an already-solved
    challenge is rejected before even writing a new Submission row,
    since there's nothing new to audit."""
    existing_solve = db.execute(
        select(models.Solve).where(models.Solve.team_id == team.id, models.Solve.challenge_id == challenge.id)
    ).scalar_one_or_none()
    if existing_solve is not None:
        raise SubmissionServiceError(409, "challenge already solved")

    expected = flags.expected_flag(challenge.box_id, team.team_secret, challenge.flag_number)
    is_correct = hmac.compare_digest(value.strip(), expected)

    submission = models.Submission(
        team_id=team.id, challenge_id=challenge.id, submitted_value=value, is_correct=is_correct
    )
    db.add(submission)
    db.flush()  # need submission.id before building the Solve row below

    if is_correct:
        db.add(models.Solve(team_id=team.id, challenge_id=challenge.id, submission_id=submission.id))

    db.commit()
    return is_correct

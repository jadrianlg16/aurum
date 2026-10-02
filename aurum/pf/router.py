"""Wires every pf sub-router under /api/pf (mounted by aurum.api.app)."""

from __future__ import annotations

from fastapi import APIRouter

from . import (
    accounts,
    accounts_admin,
    budgets,
    credit,
    entries,
    goals,
    income,
    labels,
    onboarding,
    review,
    streams,
)

router = APIRouter()
router.include_router(labels.router)
router.include_router(accounts.router)
router.include_router(accounts_admin.router)
router.include_router(entries.router)
router.include_router(streams.router)
router.include_router(income.router)
router.include_router(budgets.router)
router.include_router(goals.router)
router.include_router(credit.router)
router.include_router(review.router)
router.include_router(onboarding.router)

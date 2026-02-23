"""Signal/Wire endpoints — view incoming signals."""

from fastapi import APIRouter, Depends

from database import get_data_layer
from services.data_layer import DataLayer

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("")
async def list_signals(limit: int = 50, dl: DataLayer = Depends(get_data_layer)):
    return await dl.list_signals(limit=limit)


@router.get("/{signal_id}")
async def get_signal(signal_id: int, dl: DataLayer = Depends(get_data_layer)):
    signal = await dl.get_signal(signal_id)
    if not signal:
        return {"error": "Signal not found"}, 404
    return signal

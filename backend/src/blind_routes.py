from fastapi import APIRouter,Depends
from sqlalchemy import select
from .db import db_session
from .auth import current,writers,admin
from .blind_models import BlindBatch,BlindVerification
from .blind_schemas import BlindBatchInput,BlindSubmitInput
from . import blind_service as blind
router=APIRouter()
@router.get('/blind-batches')
def batches(s=Depends(db_session),u=Depends(current)):return [blind.batch_view(s,x) for x in s.scalars(select(BlindBatch).order_by(BlindBatch.id.desc()))]
@router.post('/blind-batches')
def seal(d:BlindBatchInput,s=Depends(db_session),u=Depends(admin)):
    x=blind.seal(s,d,u);s.commit();return x
@router.get('/blind-verifications')
def verifications(s=Depends(db_session),u=Depends(current)):return [blind.view(s,x) for x in s.scalars(select(BlindVerification).order_by(BlindVerification.id.desc()))]
@router.post('/blind-verifications')
def submit(d:BlindSubmitInput,s=Depends(db_session),u=Depends(writers)):
    x=blind.submit(s,d,u);s.commit();return x

from datetime import datetime,timezone
import numpy as np
from fastapi import HTTPException
from sqlalchemy import select
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from .models import Probe,Sweep,Pressure,Layout
from .blind_models import BlindBatch,BlindBatchSweep,BlindVerification
from .calibration_service import locked
from .services import get,pack,audit,selected,source_checksum

def now():return datetime.now(timezone.utc).isoformat()
def batched_sweep_ids(s):return set(s.scalars(select(BlindBatchSweep.sweep_id)))
def sealed_sweep_ids(s):
    return set(s.scalars(select(BlindBatchSweep.sweep_id).join(BlindBatch,BlindBatch.id==BlindBatchSweep.batch_id).where(BlindBatch.state=='sealed')))
def verification_of(s,layout_id):
    return s.scalar(select(BlindVerification).where(BlindVerification.layout_id==layout_id).order_by(BlindVerification.id.desc()))

def view(s,v):
    return pack(v)|{'batch_code':get(s,BlindBatch,v.batch_id).code,'layout_code':get(s,Layout,v.layout_id).code}
def batch_view(s,b):
    ids=list(s.scalars(select(BlindBatchSweep.sweep_id).where(BlindBatchSweep.batch_id==b.id).order_by(BlindBatchSweep.sweep_id)))
    codes={x.id:x.code for x in s.scalars(select(Sweep).where(Sweep.id.in_(ids)))} if ids else {}
    v=s.scalar(select(BlindVerification).where(BlindVerification.batch_id==b.id))
    # Lift of a sealed batch is never exposed here; the conclusion is readable only after consumption.
    return pack(b)|{'sweep_ids':ids,'sweeps':[{'id':i,'code':codes[i]} for i in ids],'verification':view(s,v) if v else None}

def seal(s,d,u):
    if len(set(d.sweep_ids))!=len(d.sweep_ids):raise HTTPException(409,'封存扫角不能重复')
    if s.scalar(select(Layout.id).where(Layout.status=='calculating')):raise HTTPException(409,'贡献计算进行中，暂不能封存扫角')
    for i in d.sweep_ids:get(s,Sweep,i)
    if s.scalar(select(BlindBatchSweep.sweep_id).where(BlindBatchSweep.sweep_id.in_(d.sweep_ids))):raise HTTPException(409,'扫角已进入其他封存批，一条扫角只能封存一次')
    b=BlindBatch(code=d.code,mae_limit=d.mae_limit,created_by=u.email,created_at=now());s.add(b);s.flush()
    for i in d.sweep_ids:s.add(BlindBatchSweep(batch_id=b.id,sweep_id=i))
    # Sealing shrinks the training pool, so stale unsigned evidence is invalidated; signed history is kept.
    for l in s.scalars(select(Layout).where(Layout.status.in_(['ready','failed']))):l.status='invalidated';l.evidence=None;l.source_checksum=None
    audit(s,u,'负责人封存盲验批 '+b.code);return batch_view(s,b)

def evaluate(s,b,ids):
    probes=[get(s,Probe,i) for i in ids]
    train=s.scalars(select(Sweep).where(Sweep.id.not_in(select(BlindBatchSweep.sweep_id))).order_by(Sweep.id)).all()
    if len(train)<40:raise HTTPException(409,'非封存扫角不足40组，不能送验')
    testsweeps=s.scalars(select(Sweep).join(BlindBatchSweep,BlindBatchSweep.sweep_id==Sweep.id).where(BlindBatchSweep.batch_id==b.id).order_by(Sweep.id)).all()
    values={(p.sweep_id,p.probe_id):p.pascal for p in s.scalars(select(Pressure))}
    try:
        x=np.array([[values[(r.id,p.id)]for p in probes]for r in train]);y=np.array([r.lift for r in train])
        xt=np.array([[values[(r.id,p.id)]for p in probes]for r in testsweeps])
    except KeyError:raise HTTPException(409,'扫角存在缺测点，不能送验')
    # Same model family as the tuning pipeline, refit on non-sealed rows only; the batch is scored blind.
    model=make_pipeline(StandardScaler(),Ridge(alpha=1.0));model.fit(x,y)
    prediction=model.predict(xt);mae=mean_absolute_error([r.lift for r in testsweeps],prediction)
    detail={'train_rows':len(train),'blind_rows':len(testsweeps),'model':'StandardScaler+Ridge(alpha=1)','selected_probe_ids':sorted(ids),'sweeps':[{'sweep':r.code,'actual':round(float(r.lift),3),'predicted':round(float(p),3)}for r,p in zip(testsweeps,prediction)]}
    return round(float(mae),3),detail

def submit(s,d,u):
    b=locked(s,BlindBatch,d.batch_id)
    existing=s.scalar(select(BlindVerification).where(BlindVerification.batch_id==b.id))
    if existing:
        # Lost-response retry of the same layout returns the original acceptance, never a duplicate.
        if existing.layout_id==d.layout_id:return view(s,existing)
        raise HTTPException(409,'本封存批资格已消耗，不能重复送验')
    if b.state!='sealed':raise HTTPException(409,'本封存批资格已消耗，不能重复送验')
    l=locked(s,Layout,d.layout_id)
    if l.status!='ready':raise HTTPException(409,'仅最新计算完成的待签方案可送验')
    checksum=source_checksum(s)
    if l.source_checksum!=checksum:raise HTTPException(409,'来源校验已变化，请重新计算后再送验')
    ids=selected(s,l.id)
    if not ids:raise HTTPException(409,'方案尚未选点，不能送验')
    mae,detail=evaluate(s,b,ids)
    v=BlindVerification(batch_id=b.id,layout_id=l.id,probe_ids=sorted(ids),source_checksum=checksum,mae=mae,mae_limit=b.mae_limit,verdict='passed' if mae<=b.mae_limit else 'failed',detail=detail,submitted_by=u.email,created_at=now())
    s.add(v)
    # Acceptance consumes the batch permanently; a failed verdict is not refunded.
    b.state='consumed';s.flush()
    audit(s,u,'送验盲批 '+b.code+' ← '+l.code+'（'+('合格' if v.verdict=='passed' else '不合格')+'）')
    return view(s,v)

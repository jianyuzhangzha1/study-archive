import os, secrets, hashlib, io
from pathlib import Path
from datetime import date, datetime, time, timezone, timedelta
from contextlib import asynccontextmanager
from collections import Counter
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from PIL import Image, UnidentifiedImageError
from .models import *
from .schemas import *

@asynccontextmanager
async def lifespan(app):
    token=os.getenv('APP_TOKEN','')
    if len(token)<24: raise RuntimeError('Set APP_TOKEN to a random secret of at least 24 characters')
    init_db();Path(os.getenv('UPLOAD_DIR','./uploads')).mkdir(parents=True,exist_ok=True)
    yield
app=FastAPI(title='学迹 · 家庭作业档案 API',version='0.1.0',lifespan=lifespan,description='单家庭开发基线。AI输出为候选，人工确认决定状态。非公共SaaS。')
security=HTTPBearer()
def auth(credentials:HTTPAuthorizationCredentials=Depends(security)):
    token=os.getenv('APP_TOKEN','')
    if len(token)<24 or not secrets.compare_digest(credentials.credentials,token): raise HTTPException(401,'认证失败')
def db():
    with Session() as s:
        try: yield s
        except (IntegrityError,StaleDataError):
            s.rollback();raise HTTPException(409,'记录冲突或已处理，请刷新后重试')
def get(s,cls,id):
    row=s.get(cls,id)
    if not row: raise HTTPException(404,'记录不存在')
    return row
def record(obj): return {col.name:getattr(obj,col.name) for col in obj.__table__.columns}
# FastAPI serializes timezone/date objects. All API mutations require a bearer token.
from fastapi import APIRouter
api=APIRouter(prefix='/api/v1',dependencies=[Depends(auth)])

@api.get('/config')
def config():
    return {'mode':os.getenv('AI_MODE','mock'),'vision_enabled':os.getenv('AI_VISION_ENABLED','false')=='true','scope':'single-family','timezone':'Asia/Shanghai'}
@api.post('/assignments',status_code=201)
def create_assignment(data:AssignmentIn,s=Depends(db)):
    a=Assignment(**{**data.model_dump(),'assigned_date':data.assigned_date.isoformat()});s.add(a);s.commit();return record(a)
@api.get('/assignments')
def list_assignments(q:str='',subject:str='',student:str='',limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),s=Depends(db)):
    stmt=select(Assignment)
    if q: stmt=stmt.where(Assignment.title.contains(q))
    if subject: stmt=stmt.where(Assignment.subject==subject)
    if student: stmt=stmt.where(Assignment.student==student)
    return [record(a) for a in s.scalars(stmt.order_by(Assignment.created_at.desc()).offset(offset).limit(limit))]
@api.get('/assignments/{id}')
def assignment(id:str,s=Depends(db)):
    a=get(s,Assignment,id)
    return {**record(a),'assets':[record(x) for x in s.scalars(select(Asset).where(Asset.assignment_id==id).order_by(Asset.page))],'questions':[record(x) for x in s.scalars(select(Question).where(Question.assignment_id==id).order_by(Question.created_at))]}
@api.post('/assignments/{id}/assets',status_code=201)
async def upload(id:str,page:int=Query(...,ge=1,le=100),file:UploadFile=File(...),s=Depends(db)):
    get(s,Assignment,id)
    raw=await file.read(12*1024*1024+1)
    if len(raw)>12*1024*1024: raise HTTPException(413,'单张图片不得超过12MiB')
    try:
        im=Image.open(io.BytesIO(raw));fmt=im.format
        if fmt not in ['JPEG','PNG','WEBP']: raise ValueError()
        if im.width*im.height>24_000_000: raise ValueError()
        im.verify()
    except (UnidentifiedImageError,ValueError,OSError,Image.DecompressionBombError): raise HTTPException(415,'仅支持24MP以内JPEG/PNG/WebP；HEIC请先转为JPEG')
    sha=hashlib.sha256(raw).hexdigest()
    prior=s.scalar(select(Asset).where(Asset.assignment_id==id,Asset.sha256==sha))
    if prior: return record(prior)
    if s.scalar(select(Asset).where(Asset.assignment_id==id,Asset.page==page)): raise HTTPException(409,'页码已占用')
    key=uid()+'.'+fmt.lower();dest=Path(os.getenv('UPLOAD_DIR','./uploads'))/key
    dest.write_bytes(raw)
    a=Asset(assignment_id=id,page=page,filename=(file.filename or 'image')[:200],storage_key=key,sha256=sha,mime={'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}[fmt],size=len(raw))
    try:s.add(a);s.commit()
    except Exception:dest.unlink(missing_ok=True);raise
    return record(a)
@api.get('/assets/{id}/content')
def asset_content(id:str,s=Depends(db)):
    a=get(s,Asset,id);return FileResponse(Path(os.getenv('UPLOAD_DIR','./uploads'))/a.storage_key,media_type=a.mime,headers={'Cache-Control':'private, no-store'})
@api.post('/assignments/{id}/questions',status_code=201)
def create_question(id:str,data:QuestionIn,s=Depends(db)):
    get(s,Assignment,id)
    if data.asset_id and get(s,Asset,data.asset_id).assignment_id!=id:raise HTTPException(422,'页面不属于此作业')
    q=Question(assignment_id=id,**data.model_dump());s.add(q);s.commit();return record(q)
@api.get('/questions/{id}')
def question(id:str,s=Depends(db)):
    q=get(s,Question,id);attempts=[]
    for a in s.scalars(select(Attempt).where(Attempt.question_id==id).order_by(Attempt.created_at)):
        f=s.scalar(select(Feedback).where(Feedback.attempt_id==a.id))
        attempts.append({**record(a),'analyses':[record(x) for x in s.scalars(select(Analysis).where(Analysis.attempt_id==a.id))],'feedback':record(f) if f else None})
    return {**record(q),'attempts':attempts}
@api.post('/questions/{id}/approve')
def approve(id:str,s=Depends(db)):
    q=get(s,Question,id);q.approved=True;q.reference_source='AI生成，家庭人工审核通过';s.commit();return record(q)
@api.post('/questions/{id}/attempts',status_code=201)
def create_attempt(id:str,data:AttemptIn,s=Depends(db)):
    q=get(s,Question,id)
    if not q.approved:raise HTTPException(409,'题目尚未审核')
    if data.purpose in ['recall','transfer']:
        if not data.review_id:raise HTTPException(422,'复测必须关联复习任务')
        r=get(s,ReviewTask,data.review_id)
        if r.question_id!=id or r.kind!=data.purpose or r.status!='pending':raise HTTPException(409,'复习任务不匹配或已处理')
        r.status='submitted'
    elif data.review_id:raise HTTPException(422,'订正与初稿不能冒充复测')
    if data.purpose=='correction':
        if not s.scalar(select(ErrorCase).where(ErrorCase.question_id==id)):raise HTTPException(409,'请先确认错题')
    a=Attempt(question_id=id,**data.model_dump());s.add(a);s.commit();return record(a)

def enqueue(s,kind,target,payload,key):
    old=s.scalar(select(Job).where(Job.request_key==key))
    if old:
        if old.kind!=kind or old.target_id!=target or old.payload!=payload:raise HTTPException(409,'幂等键被其他请求使用')
        return record(old)
    j=Job(kind=kind,target_id=target,payload=payload,request_key=key);s.add(j);s.commit();return record(j)
@api.post('/attempts/{id}/analysis-jobs',status_code=202)
def grade(id:str,idempotency_key:str=Header(...,min_length=8,max_length=100),s=Depends(db)):
    a=get(s,Attempt,id);q=get(s,Question,a.question_id);assignment=get(s,Assignment,q.assignment_id)
    return enqueue(s,'grade',id,{'subject':assignment.subject,'stem':q.stem,'reference':q.reference,'reference_source':q.reference_source,'answer':a.answer,'explanation':a.explanation,'assistance':a.assistance},idempotency_key)
@api.post('/questions/{id}/variant-jobs',status_code=202)
def variant(id:str,idempotency_key:str=Header(...,min_length=8,max_length=100),s=Depends(db)):
    q=get(s,Question,id);c=s.scalar(select(ErrorCase).where(ErrorCase.question_id==id))
    if not c:raise HTTPException(409,'请先确认错因')
    return enqueue(s,'variant',id,{'assignment_id':q.assignment_id,'stem':q.stem,'reference':q.reference,'reason':c.reason},idempotency_key)
@api.post('/assets/{id}/extraction-jobs',status_code=202)
def extraction(id:str,idempotency_key:str=Header(...,min_length=8,max_length=100),s=Depends(db)):
    a=get(s,Asset,id)
    return enqueue(s,'extract',id,{'storage_key':a.storage_key,'mime':a.mime,'page':a.page},idempotency_key)
@api.get('/jobs/{id}')
def job(id:str,s=Depends(db)):
    j=record(get(s,Job,id));j.pop('payload');return j
@api.post('/attempts/{id}/feedback',status_code=201)
def feedback(id:str,data:FeedbackIn,s=Depends(db)):
    a=get(s,Attempt,id)
    if s.scalar(select(Feedback).where(Feedback.attempt_id==id)):raise HTTPException(409,'已确认；保留原反馈，需提交新作答后复核')
    if data.analysis_id and get(s,Analysis,data.analysis_id).attempt_id!=id:raise HTTPException(422,'分析不属于该作答')
    task=get(s,ReviewTask,a.review_id) if a.review_id else None
    c=get(s,ErrorCase,task.case_id) if task else s.scalar(select(ErrorCase).where(ErrorCase.question_id==a.question_id))
    if task:
        if task.status!='submitted':raise HTTPException(409,'复测状态冲突')
        task.status='passed' if data.verdict=='correct' and a.assistance=='none' else ('uncertain' if data.verdict=='uncertain' else 'not_passed')
    if data.verdict in ['partial','incorrect']:
        if not data.reason.strip():raise HTTPException(422,'确认错题必须填写具体错因')
        if not c:
            c=ErrorCase(question_id=a.question_id,reason=data.reason);s.add(c)
        c.reason=data.reason;c.state='needs_correction'
    elif data.verdict=='correct' and c:
        # Old/original attempts cannot clear a case. Only correction and linked review events advance it.
        if a.purpose=='correction':c.state='corrected'
        elif task and a.assistance=='none':c.state='transfer_passed' if a.purpose=='transfer' else 'recall_passed'
    if c:c.updated_at=now()
    f=Feedback(attempt_id=id,**data.model_dump());s.add(f);s.commit();return record(f)
@api.get('/errors')
def errors(subject:str='',state:str='',q:str='',limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),s=Depends(db)):
    stmt=select(ErrorCase,Question,Assignment).join(Question,ErrorCase.question_id==Question.id).join(Assignment,Question.assignment_id==Assignment.id)
    if subject:stmt=stmt.where(Assignment.subject==subject)
    if state:stmt=stmt.where(ErrorCase.state==state)
    if q:stmt=stmt.where(Question.stem.contains(q)|ErrorCase.reason.contains(q))
    return [{**record(c),'stem':x.stem,'subject':a.subject,'title':a.title,'student':a.student} for c,x,a in s.execute(stmt.order_by(ErrorCase.updated_at.desc()).offset(offset).limit(limit))]
@api.post('/errors/{id}/reviews',status_code=201)
def create_review(id:str,data:ReviewIn,s=Depends(db)):
    c=get(s,ErrorCase,id);q=get(s,Question,data.question_id)
    if data.due_at.tzinfo is None:raise HTTPException(422,'due_at必须带时区')
    if data.kind=='recall' and q.id!=c.question_id:raise HTTPException(422,'原题复测必须使用原题')
    if data.kind=='transfer' and (q.source_question_id!=c.question_id or not q.approved):raise HTTPException(422,'变式必须关联原题并审核通过')
    active=s.scalar(select(ReviewTask).where(ReviewTask.case_id==id,ReviewTask.kind==data.kind,ReviewTask.status.in_(['pending','submitted'])))
    if active:raise HTTPException(409,'已有未完成的同类复测任务')
    r=ReviewTask(case_id=id,**data.model_dump());s.add(r);s.commit();return record(r)
@api.get('/reviews')
def reviews(due_only:bool=False,limit:int=Query(50,ge=1,le=100),s=Depends(db)):
    stmt=select(ReviewTask).order_by(ReviewTask.due_at)
    if due_only:stmt=stmt.where(ReviewTask.due_at<=now(),ReviewTask.status=='pending')
    return [record(r) for r in s.scalars(stmt.limit(limit))]
@api.get('/reports/summary')
def report(start:date|None=None,end:date|None=None,subject:str='',student:str='',s=Depends(db)):
    if start and end and start>end:raise HTTPException(422,'日期范围错误')
    # Reporting cohort is assignment date, not feedback creation date. Explicitly documented.
    stmt=select(Assignment)
    if start:stmt=stmt.where(Assignment.assigned_date>=start.isoformat())
    if end:stmt=stmt.where(Assignment.assigned_date<=end.isoformat())
    if subject:stmt=stmt.where(Assignment.subject==subject)
    if student:stmt=stmt.where(Assignment.student==student)
    aids=[a.id for a in s.scalars(stmt)]
    qids=list(s.scalars(select(Question.id).where(Question.assignment_id.in_(aids),Question.approved==True)))
    attempts=list(s.scalars(select(Attempt).where(Attempt.question_id.in_(qids))))
    cases=list(s.scalars(select(ErrorCase).where(ErrorCase.question_id.in_(qids))))
    feedbacks=list(s.scalars(select(Feedback).where(Feedback.attempt_id.in_([a.id for a in attempts]))))
    original={a.id for a in attempts if a.purpose=='original' and a.assistance=='none'}
    eligible=[f for f in feedbacks if f.attempt_id in original and f.verdict!='uncertain']
    return {'cohort':'作业日期范围；非全校成绩，不计未确认AI意见；初稿按作答次数统计','assignments':len(aids),'questions':len(qids),'attempts':len(attempts),'confirmed_errors':len(cases),'error_states':dict(Counter(c.state for c in cases)),'reasons':dict(Counter(c.reason for c in cases)),'independent_original':{'correct':sum(f.verdict=='correct' for f in eligible),'denominator':len(eligible)},'assisted_attempts':sum(a.assistance!='none' for a in attempts),'ai_mode':os.getenv('AI_MODE','mock')}
@api.get('/export')
def export(s=Depends(db)):
    classes=[Assignment,Asset,Question,Attempt,Job,Analysis,ErrorCase,Feedback,ReviewTask,KnowledgeNode,QuestionKnowledge]
    return {'format':'study-archive.v1','exported_at':now(),'tables':{c.__tablename__:[record(x) for x in s.scalars(select(c))] for c in classes},'attachments':'需同时备份上传目录；此JSON不含图片字节'}

app.include_router(api)
@app.get('/healthz')
def health():return {'status':'ok','version':'0.1.0'}
@app.get('/')
def home():return FileResponse(Path(__file__).parent.parent/'web'/'index.html')
app.mount('/static',StaticFiles(directory=Path(__file__).parent.parent/'web'),name='static')

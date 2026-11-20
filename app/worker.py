import time, os
from datetime import timedelta
from sqlalchemy import select, update
from .models import Session, Job, Analysis, Question, now, init_db
from .ai import invoke, PROMPT_VERSION

def process_one():
    with Session() as s:
        # After a crash mark expired leases explicitly; never silently repeat a paid call.
        s.execute(update(Job).where(Job.status=='running',Job.started_at<now()-timedelta(minutes=5)).values(status='failed',error='worker lease expired; manual retry required'))
        s.commit()
        j=s.scalar(select(Job).where(Job.status=='queued').order_by(Job.created_at).limit(1))
        if not j: return False
        claim=s.execute(update(Job).where(Job.id==j.id,Job.status=='queued').values(status='running',started_at=now()))
        s.commit()
        if claim.rowcount!=1: return True
        s.refresh(j)
        try:
            result,usage,provider,model=invoke(j.kind,j.payload)
            if j.kind=='grade':
                a=Analysis(attempt_id=j.target_id,job_id=j.id,provider=provider,model=model,prompt_version=PROMPT_VERSION,result=result,usage=usage)
                s.add(a);s.flush();result={**result,'analysis_id':a.id}
            elif j.kind=='variant':
                q=Question(assignment_id=j.payload['assignment_id'],source_question_id=j.target_id,number='变式候选',stem=result['stem'],reference=result['reference'],reference_source='AI生成，待人工审核',approved=False)
                s.add(q);s.flush();result={**result,'question_id':q.id}
            j.result=result;j.status='succeeded';j.finished_at=now();s.commit()
        except Exception as exc:
            s.rollback();j=s.get(Job,j.id);j.status='failed';j.finished_at=now()
            # No request payloads, provider bodies, or secrets in logs/API error messages.
            j.error=type(exc).__name__+': 处理失败；检查配置、服务响应或输出校验，人工重试。';s.commit()
    return True
if __name__=='__main__':
    init_db()
    while True:
        if not process_one(): time.sleep(2)

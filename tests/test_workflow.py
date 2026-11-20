import os, tempfile, io
from pathlib import Path
ROOT=Path(tempfile.mkdtemp(prefix='study-test-'))
os.environ.update(DATABASE_URL='sqlite:///'+str(ROOT/'test.db'),UPLOAD_DIR=str(ROOT/'uploads'),APP_TOKEN='test-secret-token-with-32-characters',AI_MODE='mock')
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
from app.models import Session, Question, Job, Analysis, ErrorCase, Base, engine
from app.worker import process_one
import pytest

@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        c.headers['Authorization']='Bearer '+os.environ['APP_TOKEN']
        yield c

def create(c):
    a=c.post('/api/v1/assignments',json={'title':'数学测试','subject':'数学','student':'测试学生','assigned_date':'2026-11-08'}).json()
    q=c.post('/api/v1/assignments/'+a['id']+'/questions',json={'number':'1','stem':'2x=4，求x','reference':'x=2','reference_source':'测试人工答案'}).json()
    return a,q

def attempt(c,q,**kw):
    r=c.post('/api/v1/questions/'+q['id']+'/attempts',json={'answer':'x=3',**kw});assert r.status_code==201,r.text;return r.json()
def confirm(c,a,verdict='incorrect',reason='计算错误'):
    return c.post('/api/v1/attempts/'+a['id']+'/feedback',json={'verdict':verdict,'reason':reason,'reviewer':'测试家长'})
def test_auth(client):
    assert client.get('/api/v1/assignments',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert client.get('/healthz').status_code==200

def test_complete_loop(client):
    c=client;a,q=create(c);x=attempt(c,q)
    url='/api/v1/attempts/'+x['id']+'/analysis-jobs';h={'Idempotency-Key':'request-0001'}
    j=c.post(url,headers=h).json();assert c.post(url,headers=h).json()['id']==j['id']
    assert process_one();assert c.get('/api/v1/jobs/'+j['id']).json()['status']=='succeeded'
    assert c.get('/api/v1/errors').json()==[] # AI never creates confirmed errors
    assert confirm(c,x).status_code==201
    case=c.get('/api/v1/errors').json()[0]
    revised=attempt(c,q,purpose='correction',answer='x=2',assistance='hint')
    assert confirm(c,revised,'correct','').status_code==201
    assert c.get('/api/v1/errors').json()[0]['state']=='corrected'
    r=c.post('/api/v1/errors/'+case['id']+'/reviews',json={'kind':'recall','question_id':q['id'],'due_at':'2026-11-09T18:00:00+08:00'}).json()
    x=attempt(c,q,purpose='recall',answer='x=2',assistance='none',review_id=r['id'])
    assert confirm(c,x,'correct','').status_code==201
    assert c.get('/api/v1/errors').json()[0]['state']=='recall_passed'
    assert confirm(c,x,'incorrect').status_code==409
    # Transfer candidates are not eligible until reviewed.
    with Session() as s:
        variant=Question(assignment_id=a['id'],source_question_id=q['id'],number='变式',stem='3x=9',reference='x=3',approved=False);s.add(variant);s.commit();vid=variant.id
    body={'kind':'transfer','question_id':vid,'due_at':'2026-11-10T18:00:00+08:00'}
    assert c.post('/api/v1/errors/'+case['id']+'/reviews',json=body).status_code==422
    c.post('/api/v1/questions/'+vid+'/approve')
    r=c.post('/api/v1/errors/'+case['id']+'/reviews',json=body).json()
    x=attempt(c,{'id':vid},purpose='transfer',answer='x=3',review_id=r['id'])
    assert confirm(c,x,'correct','').status_code==201
    assert c.get('/api/v1/errors').json()[0]['state']=='transfer_passed'
    report=c.get('/api/v1/reports/summary').json();assert report['independent_original']=={'correct':0,'denominator':1}
    assert report['assisted_attempts']==1

def test_assisted_review_not_passed(client):
    c=client;a,q=create(c);x=attempt(c,q);confirm(c,x);case=c.get('/api/v1/errors').json()[0]
    r=c.post('/api/v1/errors/'+case['id']+'/reviews',json={'kind':'recall','question_id':q['id'],'due_at':'2026-11-09T18:00:00+08:00'}).json()
    x=attempt(c,q,purpose='recall',answer='x=2',assistance='answer',review_id=r['id']);confirm(c,x,'correct','')
    assert c.get('/api/v1/reviews').json()[0]['status']=='not_passed'
    assert c.get('/api/v1/errors').json()[0]['state']=='needs_correction'

def test_invalid_cross_links(client):
    c=client;a,q=create(c);a2,q2=create(c);x=attempt(c,q)
    j=c.post('/api/v1/attempts/'+x['id']+'/analysis-jobs',headers={'Idempotency-Key':'request-cross'}).json();process_one()
    aid=c.get('/api/v1/jobs/'+j['id']).json()['result']['analysis_id']
    x2=attempt(c,q2)
    r=c.post('/api/v1/attempts/'+x2['id']+'/feedback',json={'verdict':'correct','reason':'','reviewer':'家长','analysis_id':aid});assert r.status_code==422
    assert c.post('/api/v1/questions/'+q['id']+'/attempts',json={'answer':'x=2','purpose':'transfer'}).status_code==422
    assert c.post('/api/v1/attempts/'+x2['id']+'/analysis-jobs',headers={'Idempotency-Key':'request-cross'}).status_code==409

def test_upload_validation_and_roundtrip(client):
    c=client;a,q=create(c);img=io.BytesIO();Image.new('RGB',(20,20),'white').save(img,format='PNG');data=img.getvalue()
    url='/api/v1/assignments/'+a['id']+'/assets?page=1'
    assert c.post(url,files={'file':('bad.png',b'not an image','image/png')}).status_code==415
    r=c.post(url,files={'file':('a.png',data,'image/png')});assert r.status_code==201,r.text
    asset=r.json();assert c.get('/api/v1/assets/'+asset['id']+'/content').content==data
    assert c.post(url,files={'file':('copy.png',data,'image/png')}).json()['id']==asset['id']
    assert c.get('/api/v1/export').json()['tables']['assets'][0]['sha256']==asset['sha256']

def test_ai_invalid_output_does_not_mutate(client,monkeypatch):
    c=client;a,q=create(c);x=attempt(c,q)
    j=c.post('/api/v1/attempts/'+x['id']+'/analysis-jobs',headers={'Idempotency-Key':'request-failed'}).json()
    def fail(*args):raise ValueError('secret should not leak')
    monkeypatch.setattr('app.worker.invoke',fail);process_one()
    result=c.get('/api/v1/jobs/'+j['id']).json();assert result['status']=='failed';assert 'secret' not in result['error'];assert c.get('/api/v1/errors').json()==[]

def test_report_range(client):
    create(client)
    assert client.get('/api/v1/reports/summary?start=2026-11-09').json()['assignments']==0
    assert client.get('/api/v1/reports/summary?start=2026-11-10&end=2026-11-01').status_code==422

def test_duplicate_pending_review_rejected(client):
    c=client;a,q=create(c);x=attempt(c,q);confirm(c,x);case=c.get('/api/v1/errors').json()[0]
    body={'kind':'recall','question_id':q['id'],'due_at':'2026-11-09T18:00:00+08:00'}
    assert c.post('/api/v1/errors/'+case['id']+'/reviews',json=body).status_code==201
    assert c.post('/api/v1/errors/'+case['id']+'/reviews',json=body).status_code==409

def test_ai_quote_must_exist(monkeypatch):
    import json
    from app.ai import invoke
    monkeypatch.setenv('AI_MODE','openai-compatible');monkeypatch.setenv('AI_BASE_URL','https://example.test/v1');monkeypatch.setenv('AI_API_KEY','test');monkeypatch.setenv('AI_MODEL','test')
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'choices':[{'message':{'content':json.dumps({'verdict':'incorrect','summary':'test','issues':[{'quote':'invented quote','reason':'x','suggestion':'x'}],'next_question':'x'})}}]}
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,*args,**kw):return Response()
    monkeypatch.setattr('app.ai.httpx.Client',Client)
    with pytest.raises(ValueError,match='quote'):invoke('grade',{'answer':'actual student answer'})

def test_mock_does_not_fake_variant(monkeypatch):
    from app.ai import invoke
    monkeypatch.setenv('AI_MODE','mock')
    with pytest.raises(RuntimeError,match='演示模式'):invoke('variant',{})

from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')
class AssignmentIn(Input):
    title:str=Field(min_length=1,max_length=200)
    subject:Literal['数学','英语','语文']
    student:str=Field(min_length=1,max_length=80)
    assigned_date:date
class QuestionIn(Input):
    number:str=Field(min_length=1,max_length=30)
    stem:str=Field(min_length=1,max_length=20000)
    reference:str=Field(default='',max_length=20000)
    reference_source:str=Field(default='未提供',max_length=100)
    asset_id:str|None=None
class AttemptIn(Input):
    purpose:Literal['original','correction','recall','transfer']='original'
    answer:str=Field(min_length=1,max_length=20000)
    explanation:str=Field(default='',max_length=5000)
    assistance:Literal['none','hint','example','answer']='none'
    review_id:str|None=None
class FeedbackIn(Input):
    verdict:Literal['correct','partial','incorrect','uncertain']
    reason:str=Field(default='',max_length=200)
    note:str=Field(default='',max_length=5000)
    reviewer:str=Field(min_length=1,max_length=80)
    analysis_id:str|None=None
class ReviewIn(Input):
    kind:Literal['recall','transfer']
    question_id:str
    due_at:datetime
class Issue(Input):
    quote:str=Field(max_length=2000)
    reason:str=Field(max_length=1000)
    suggestion:str=Field(max_length=2000)
class GradeResult(Input):
    verdict:Literal['correct','partial','incorrect','uncertain']
    summary:str=Field(max_length=4000)
    issues:list[Issue]=Field(max_length=10)
    next_question:str=Field(max_length=2000)
class VariantResult(Input):
    stem:str=Field(min_length=1,max_length=10000)
    reference:str=Field(min_length=1,max_length=10000)
    rationale:str=Field(max_length=4000)
class ExtractionResult(Input):
    text:str=Field(max_length=30000)
    uncertain_regions:list[str]=Field(max_length=100)

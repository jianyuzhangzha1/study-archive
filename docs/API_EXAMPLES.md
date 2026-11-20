# 对外接口使用示例

所有业务接口使用Authorization: Bearer <APP_TOKEN>，令牌只由后端配置。生产API密钥不是APP_TOKEN；两者不得混用。

## 新建作业

`POST /api/v1/assignments`

```json
{"title":"函数定义域练习","subject":"数学","student":"学生一","assigned_date":"2026-11-08"}
```

返回201，含id、created_at及提交字段。保存返回id，禁止假定ID有自增顺序。

## 新建题目

`POST /api/v1/assignments/{assignment_id}/questions`

```json
{"number":"3","stem":"求f(x)=1/(x−2)的定义域。","reference":"x≠2","reference_source":"教师提供","asset_id":null}
```

返回201，含题目id、approved=true。asset_id如存在，必须属于同一作业。

## 保存初稿

`POST /api/v1/questions/{question_id}/attempts`

```json
{"purpose":"original","answer":"全体实数","explanation":"我只看了x是实数。","assistance":"none","review_id":null}
```

返回201及不可变attempt_id。订正用purpose=correction，仍创建新记录。复测用recall或transfer，必须提交review_id。

## 提交AI初审

`POST /api/v1/attempts/{attempt_id}/analysis-jobs`

额外请求头：`Idempotency-Key: your-random-unique-key`。无请求正文。

返回202示意：

```json
{"id":"<job_id>","kind":"grade","target_id":"<attempt_id>","status":"queued","request_key":"your-random-unique-key","result":null,"error":null}
```

提交响应也包含内部payload和时间字段；轮询GET /jobs/{job_id}会省略payload。不要把响应完整写入公共日志。

成功result包含verdict、summary、issues、next_question、analysis_id。UI必须显示“AI初审”；此时错题状态不会改变。

## 人工确认

`POST /api/v1/attempts/{attempt_id}/feedback`

```json
{"verdict":"incorrect","reason":"遗漏分母不为零的条件","note":"检查表达式的约束后重新作答。","reviewer":"家长","analysis_id":"<analysis_id>"}
```

没有AI分析时analysis_id可为null。返回201，事务性保存反馈并创建/更新错题状态。重复确认返回409。

## 安排回顾

`POST /api/v1/errors/{error_case_id}/reviews`

```json
{"kind":"recall","question_id":"<original_question_id>","due_at":"2026-11-11T18:00:00+08:00"}
```

同类验证改kind=transfer，并使用已经审核且source_question_id指向原题的题目。

## 查询报表

`GET /api/v1/reports/summary?start=2026-11-01&end=2026-11-08&subject=数学`

示例返回：

```json
{
  "cohort":"作业日期范围；非全校成绩，不计未确认AI意见；初稿按作答次数统计",
  "assignments":1,
  "questions":1,
  "attempts":3,
  "confirmed_errors":1,
  "error_states":{"recall_passed":1},
  "reasons":{"遗漏分母不为零的条件":1},
  "independent_original":{"correct":0,"denominator":1},
  "assisted_attempts":1,
  "ai_mode":"mock"
}
```

此处数值为说明样例，不是任何真实学生成绩。接口输出直接JSON，无统一data包装。完整请求验证结构见openapi.json；当前响应主要为动态对象，未来可补充强类型response_model并生成客户端SDK。

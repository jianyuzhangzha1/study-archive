-- Initial schema v0.1.0; generated from app/models.py.
-- Application supplies UUIDs and timestamps. No seed personal data.
BEGIN;

CREATE TABLE assignments (
	title VARCHAR(200) NOT NULL, 
	subject VARCHAR(20) NOT NULL, 
	student VARCHAR(80) NOT NULL, 
	assigned_date VARCHAR(10) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE jobs (
	kind VARCHAR(20) NOT NULL, 
	target_id VARCHAR(36) NOT NULL, 
	request_key VARCHAR(100) NOT NULL, 
	payload JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	result JSON, 
	error TEXT, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (request_key)
)

;
CREATE INDEX ix_jobs_status ON jobs (status);

CREATE TABLE knowledge_nodes (
	code VARCHAR(80) NOT NULL, 
	subject VARCHAR(20) NOT NULL, 
	label VARCHAR(200) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	source VARCHAR(200) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
)

;

CREATE TABLE assets (
	assignment_id VARCHAR(36) NOT NULL, 
	filename VARCHAR(200) NOT NULL, 
	storage_key VARCHAR(100) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	mime VARCHAR(50) NOT NULL, 
	size INTEGER NOT NULL, 
	page INTEGER NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (assignment_id, page), 
	FOREIGN KEY(assignment_id) REFERENCES assignments (id)
)

;
CREATE INDEX ix_assets_assignment_id ON assets (assignment_id);

CREATE TABLE questions (
	assignment_id VARCHAR(36) NOT NULL, 
	source_question_id VARCHAR(36), 
	asset_id VARCHAR(36), 
	number VARCHAR(30) NOT NULL, 
	stem TEXT NOT NULL, 
	reference TEXT NOT NULL, 
	reference_source VARCHAR(100) NOT NULL, 
	approved BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(assignment_id) REFERENCES assignments (id), 
	FOREIGN KEY(source_question_id) REFERENCES questions (id), 
	FOREIGN KEY(asset_id) REFERENCES assets (id)
)

;
CREATE INDEX ix_questions_assignment_id ON questions (assignment_id);

CREATE TABLE error_cases (
	question_id VARCHAR(36) NOT NULL, 
	state VARCHAR(30) NOT NULL, 
	reason VARCHAR(200) NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	version INTEGER NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (question_id), 
	FOREIGN KEY(question_id) REFERENCES questions (id)
)

;

CREATE TABLE question_knowledge (
	question_id VARCHAR(36) NOT NULL, 
	node_id VARCHAR(36) NOT NULL, 
	relation VARCHAR(20) NOT NULL, 
	PRIMARY KEY (question_id, node_id), 
	FOREIGN KEY(question_id) REFERENCES questions (id), 
	FOREIGN KEY(node_id) REFERENCES knowledge_nodes (id)
)

;

CREATE TABLE review_tasks (
	case_id VARCHAR(36) NOT NULL, 
	question_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	due_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES error_cases (id), 
	FOREIGN KEY(question_id) REFERENCES questions (id)
)

;
CREATE INDEX ix_review_tasks_case_id ON review_tasks (case_id);
CREATE INDEX ix_review_tasks_due_at ON review_tasks (due_at);
CREATE UNIQUE INDEX uq_active_review ON review_tasks (case_id, kind) WHERE status IN ('pending','submitted');

CREATE TABLE attempts (
	question_id VARCHAR(36) NOT NULL, 
	purpose VARCHAR(20) NOT NULL, 
	answer TEXT NOT NULL, 
	explanation TEXT NOT NULL, 
	assistance VARCHAR(20) NOT NULL, 
	review_id VARCHAR(36), 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (review_id), 
	FOREIGN KEY(question_id) REFERENCES questions (id), 
	FOREIGN KEY(review_id) REFERENCES review_tasks (id)
)

;
CREATE INDEX ix_attempts_question_id ON attempts (question_id);

CREATE TABLE analyses (
	attempt_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	provider VARCHAR(50) NOT NULL, 
	model VARCHAR(100) NOT NULL, 
	prompt_version VARCHAR(40) NOT NULL, 
	result JSON NOT NULL, 
	usage JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(attempt_id) REFERENCES attempts (id), 
	UNIQUE (job_id), 
	FOREIGN KEY(job_id) REFERENCES jobs (id)
)

;
CREATE INDEX ix_analyses_attempt_id ON analyses (attempt_id);

CREATE TABLE feedback (
	attempt_id VARCHAR(36) NOT NULL, 
	analysis_id VARCHAR(36), 
	verdict VARCHAR(20) NOT NULL, 
	reason VARCHAR(200) NOT NULL, 
	note TEXT NOT NULL, 
	reviewer VARCHAR(80) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (attempt_id), 
	FOREIGN KEY(attempt_id) REFERENCES attempts (id), 
	FOREIGN KEY(analysis_id) REFERENCES analyses (id)
)

;
COMMIT;
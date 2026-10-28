CREATE TABLE IF NOT EXISTS attempts (
  id VARCHAR(64) PRIMARY KEY,
  title VARCHAR(200) NOT NULL,
  idea TEXT NOT NULL,
  mechanism TEXT NOT NULL,
  task VARCHAR(100) NOT NULL,
  domain VARCHAR(100) NOT NULL,
  failure_condition TEXT NOT NULL,
  assumptions JSON NOT NULL,
  competing_explanations JSON NOT NULL,
  differentiator TEXT,
  embedding VECTOR(64) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  historical_decision VARCHAR(40),
  revision INT NOT NULL DEFAULT 1,
  available_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL,
  gpu_count INT NOT NULL,
  data_ready BOOLEAN NOT NULL,
  checkpoint_ready BOOLEAN NOT NULL,
  pilot_hours DOUBLE NOT NULL,
  storage_gb DOUBLE NOT NULL,
  baseline_first BOOLEAN NOT NULL,
  FULLTEXT INDEX ft_attempt_mechanism (idea, mechanism, failure_condition) WITH PARSER ik,
  VECTOR INDEX idx_attempt_embedding (embedding) WITH (DISTANCE=l2, TYPE=hnsw, LIB=vsag),
  INDEX idx_attempt_time (available_at),
  INDEX idx_attempt_scope (task, domain, status)
) ORGANIZATION = HEAP;

CREATE TABLE IF NOT EXISTS evidence (
  id VARCHAR(100) PRIMARY KEY,
  attempt_id VARCHAR(64) NOT NULL,
  source_type VARCHAR(40) NOT NULL,
  title VARCHAR(300) NOT NULL,
  locator TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  stance VARCHAR(20) NOT NULL,
  published_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_evidence_attempt_time (attempt_id, published_at)
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
  id VARCHAR(64) PRIMARY KEY,
  attempt_id VARCHAR(64) NOT NULL,
  cutoff DATETIME NOT NULL,
  snapshot_hash CHAR(64) NOT NULL,
  model_version VARCHAR(100) NOT NULL,
  embedding_version VARCHAR(100) NOT NULL,
  rules_version VARCHAR(100) NOT NULL,
  context_refs JSON,
  machine_decision VARCHAR(40) NOT NULL,
  reason_code VARCHAR(100) NOT NULL,
  report JSON NOT NULL,
  replay_of VARCHAR(64),
  created_at DATETIME NOT NULL,
  INDEX idx_runs_attempt (attempt_id, created_at)
);

CREATE TABLE IF NOT EXISTS comparisons (
  id VARCHAR(64) PRIMARY KEY,
  run_id VARCHAR(64) NOT NULL,
  historical_attempt_id VARCHAR(64) NOT NULL,
  vector_distance DOUBLE,
  fts_score DOUBLE,
  fused_score DOUBLE NOT NULL,
  mechanism_difference TEXT NOT NULL,
  evidence_ids JSON NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_comparisons_run (run_id)
);

CREATE TABLE IF NOT EXISTS check_results (
  id VARCHAR(64) PRIMARY KEY,
  run_id VARCHAR(64) NOT NULL,
  check_name VARCHAR(100) NOT NULL,
  status VARCHAR(20) NOT NULL,
  reason_code VARCHAR(100) NOT NULL,
  detail TEXT NOT NULL,
  evidence_ids JSON NOT NULL,
  checker_version VARCHAR(100) NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_checks_run (run_id)
);

CREATE TABLE IF NOT EXISTS decisions (
  id VARCHAR(64) PRIMARY KEY,
  run_id VARCHAR(64) NOT NULL,
  attempt_id VARCHAR(64) NOT NULL,
  decision VARCHAR(40) NOT NULL,
  reason TEXT NOT NULL,
  restart_conditions TEXT,
  reviewer_alias VARCHAR(100) NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_decisions_attempt (attempt_id, created_at)
);

CREATE TABLE IF NOT EXISTS experiments (
  id VARCHAR(64) PRIMARY KEY,
  attempt_id VARCHAR(64) NOT NULL,
  hypothesis TEXT NOT NULL,
  intervention TEXT NOT NULL,
  control TEXT NOT NULL,
  metric VARCHAR(500) NOT NULL,
  threshold VARCHAR(500) NOT NULL,
  observed_result TEXT NOT NULL,
  outcome VARCHAR(20) NOT NULL,
  stop_triggered BOOLEAN NOT NULL,
  ran_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_experiments_attempt (attempt_id, ran_at)
);

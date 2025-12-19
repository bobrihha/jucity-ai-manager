CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS parks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text NOT NULL UNIQUE,
  name text NOT NULL,
  base_url text NOT NULL,
  active_kb_index_id uuid NULL
);

CREATE TABLE IF NOT EXISTS park_locations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  address_text text NOT NULL,
  city text,
  lat double precision,
  lon double precision
);

CREATE TABLE IF NOT EXISTS park_contacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  type text NOT NULL,
  value text NOT NULL,
  is_primary boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS park_opening_hours (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  dow int NOT NULL CHECK (dow BETWEEN 0 AND 6),
  open_time time,
  close_time time,
  is_closed boolean NOT NULL DEFAULT false,
  note text
);

CREATE TABLE IF NOT EXISTS park_transport (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  kind text NOT NULL,
  text text NOT NULL
);

CREATE TABLE IF NOT EXISTS site_pages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  key text NOT NULL,
  path text,
  absolute_url text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (park_id, key)
);

CREATE TABLE IF NOT EXISTS legal_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  key text NOT NULL,
  title text NOT NULL,
  path text,
  absolute_url text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS promotions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  key text NOT NULL,
  title text NOT NULL,
  text text NOT NULL,
  valid_from timestamptz,
  valid_to timestamptz,
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (park_id, key)
);

CREATE TABLE IF NOT EXISTS faq (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  question text NOT NULL,
  answer text NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  ts_utc timestamptz GENERATED ALWAYS AS (created_at) STORED,
  trace_id uuid NOT NULL,
  session_id uuid NOT NULL,
  user_id text,
  park_id uuid,
  park_slug text,
  channel text,
  event_name text NOT NULL,
  facts_version_id uuid NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload_json jsonb GENERATED ALWAYS AS (payload) STORED
);

CREATE INDEX IF NOT EXISTS event_log_trace_id_idx ON event_log(trace_id);
CREATE INDEX IF NOT EXISTS event_log_created_at_idx ON event_log(created_at);

CREATE TABLE IF NOT EXISTS kb_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  enabled boolean NOT NULL DEFAULT true,
  source_type text NOT NULL, -- url|pdf|file_path
  source_url text,
  file_path text,
  title text,
  content_type text,
  last_hash text,
  last_fetched_at timestamptz,
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS kb_sources_park_enabled_idx ON kb_sources(park_id) WHERE enabled = true;

CREATE TABLE IF NOT EXISTS kb_indexes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  label text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz,
  status text NOT NULL DEFAULT 'created'
);

CREATE INDEX IF NOT EXISTS kb_indexes_park_created_idx ON kb_indexes(park_id, created_at DESC);

CREATE TABLE IF NOT EXISTS kb_index_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'queued', -- queued|running|success|failed
  triggered_by text,
  reason text,
  sources_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  stats_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_text text,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz
);

CREATE INDEX IF NOT EXISTS kb_index_jobs_park_created_idx ON kb_index_jobs(park_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS kb_index_jobs_one_active_per_park_idx
  ON kb_index_jobs(park_id)
  WHERE status IN ('queued','running');

CREATE TABLE IF NOT EXISTS leads (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  status text NOT NULL DEFAULT 'open',

  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  session_id uuid NOT NULL,

  intent text,
  client_phone text,
  client_name text,

  event_type text,
  event_date date,
  event_time time,
  day_of_week int,

  kids_count int,
  kids_age_main int,
  adults_count int,

  need_room boolean,
  need_banquet boolean,
  add_ons text,

  conversation_summary text,
  conversation_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  missing_required_slots jsonb NOT NULL DEFAULT '[]'::jsonb,

  admin_message text
);

CREATE INDEX IF NOT EXISTS leads_session_id_idx ON leads(session_id);
CREATE INDEX IF NOT EXISTS leads_park_session_open_idx ON leads(park_id, session_id) WHERE status <> 'closed';

CREATE TABLE IF NOT EXISTS facts_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
  status text NOT NULL, -- draft|published|archived
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  published_by text,
  notes text
);

CREATE INDEX IF NOT EXISTS facts_versions_park_pub_idx ON facts_versions(park_id, published_at DESC);

CREATE TABLE IF NOT EXISTS facts_snapshots (
  facts_version_id uuid PRIMARY KEY REFERENCES facts_versions(id) ON DELETE CASCADE,
  snapshot_json jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS park_published_state (
  park_id uuid PRIMARY KEY REFERENCES parks(id) ON DELETE CASCADE,
  published_version_id uuid NOT NULL REFERENCES facts_versions(id) ON DELETE RESTRICT,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS change_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  park_id uuid,
  actor text NOT NULL,
  entity_table text NOT NULL,
  action text NOT NULL,
  before_json jsonb,
  after_json jsonb,
  reason text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS change_log_park_created_idx ON change_log(park_id, created_at DESC);

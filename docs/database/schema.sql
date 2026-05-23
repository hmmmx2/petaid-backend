-- =====================================================================
--  PetAid - PostgreSQL schema (SWE30003 Assignment 3, database design)
--
--  Generated from the canonical SQLAlchemy 2.0 ORM models in
--  petaid-backend/app/models/. This is the authoritative relational
--  realisation of the object-oriented domain model.
--
--  HOW TO USE (Supabase):
--    Supabase Dashboard -> SQL Editor -> New query -> paste this file -> Run.
--    Then open  Database -> Schema Visualizer  to export the ERD for the report.
--    (Run once, on an empty `public` schema.)
--
--  OO -> relational mapping notes:
--    * Account / PetOwner / VeterinaryExpert -> single-table inheritance on
--      `accounts.role` (discriminator column).
--    * Composition (UserCredentials, DonationRecord, FeedbackEntry) -> child
--      table with a UNIQUE FK + ON DELETE CASCADE (cannot outlive its owner).
--    * Aggregation (Pet, Inquiry, Chat, Donation, QuizAttempt, Feedback) -> FK
--      to the owning Account.
--    * Many-to-many (FirstAidGuidance <-> Resource) -> `first_aid_resource_link`.
--    * Polymorphic Feedback target -> (target_type, target_id) pair.
--    * Value-object lists (steps, questions, answers, image_urls) -> JSONB.
--  UUID primary keys default to gen_random_uuid(); the application also
--  supplies its own UUIDs, so either insert path works.
-- =====================================================================

create extension if not exists pgcrypto;


CREATE TABLE accounts (
	full_name VARCHAR(120) NOT NULL, 
	initials VARCHAR(4) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	email_verified BOOLEAN NOT NULL, 
	role VARCHAR(40) NOT NULL, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_accounts_role ON accounts (role);

CREATE TABLE pet_types (
	name VARCHAR(60) NOT NULL, 
	description VARCHAR(240) NOT NULL, 
	icon_emoji VARCHAR(8) NOT NULL, 
	icon_bg VARCHAR(16) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_pet_types_name ON pet_types (name);

CREATE TABLE chats (
	pet_owner_id UUID NOT NULL, 
	vet_id UUID, 
	subject VARCHAR(160) NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	ended_at TIMESTAMP WITH TIME ZONE, 
	owner_last_read_at TIMESTAMP WITH TIME ZONE, 
	vet_last_read_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pet_owner_id) REFERENCES accounts (id) ON DELETE CASCADE, 
	FOREIGN KEY(vet_id) REFERENCES accounts (id) ON DELETE SET NULL
);
CREATE INDEX ix_chats_pet_owner_id ON chats (pet_owner_id);
CREATE INDEX ix_chats_status ON chats (status);
CREATE INDEX ix_chats_vet_id ON chats (vet_id);

CREATE TABLE donations (
	pet_owner_id UUID NOT NULL, 
	amount_cents INTEGER NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	recurring BOOLEAN NOT NULL, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pet_owner_id) REFERENCES accounts (id) ON DELETE CASCADE
);
CREATE INDEX ix_donations_pet_owner_id ON donations (pet_owner_id);
CREATE INDEX ix_donations_status ON donations (status);

CREATE TABLE feedback (
	submitter_id UUID NOT NULL, 
	target_type VARCHAR(8) NOT NULL, 
	target_id UUID NOT NULL, 
	flagged BOOLEAN NOT NULL, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(submitter_id) REFERENCES accounts (id) ON DELETE CASCADE
);
CREATE INDEX ix_feedback_flagged ON feedback (flagged);
CREATE INDEX ix_feedback_submitter_id ON feedback (submitter_id);
CREATE INDEX ix_feedback_target_id ON feedback (target_id);
CREATE INDEX ix_feedback_target_type ON feedback (target_type);

CREATE TABLE first_aid_guidance (
	pet_type_id UUID NOT NULL, 
	author_id UUID NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	emergency_type VARCHAR(60) NOT NULL, 
	summary TEXT NOT NULL, 
	steps JSONB NOT NULL, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pet_type_id) REFERENCES pet_types (id) ON DELETE RESTRICT, 
	FOREIGN KEY(author_id) REFERENCES accounts (id) ON DELETE RESTRICT
);
CREATE INDEX ix_first_aid_guidance_author_id ON first_aid_guidance (author_id);
CREATE INDEX ix_first_aid_guidance_emergency_type ON first_aid_guidance (emergency_type);
CREATE INDEX ix_first_aid_guidance_pet_type_id ON first_aid_guidance (pet_type_id);

CREATE TABLE inquiries (
	pet_owner_id UUID NOT NULL, 
	assigned_vet_id UUID, 
	subject VARCHAR(160) NOT NULL, 
	question TEXT NOT NULL, 
	response TEXT, 
	image_urls JSONB DEFAULT '[]' NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	submitted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	responded_at TIMESTAMP WITH TIME ZONE, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pet_owner_id) REFERENCES accounts (id) ON DELETE CASCADE, 
	FOREIGN KEY(assigned_vet_id) REFERENCES accounts (id) ON DELETE SET NULL
);
CREATE INDEX ix_inquiries_assigned_vet_id ON inquiries (assigned_vet_id);
CREATE INDEX ix_inquiries_pet_owner_id ON inquiries (pet_owner_id);
CREATE INDEX ix_inquiries_status ON inquiries (status);

CREATE TABLE pets (
	owner_id UUID NOT NULL, 
	pet_type_id UUID NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	breed VARCHAR(80), 
	age_years INTEGER, 
	health_notes TEXT NOT NULL, 
	image_url TEXT, 
	icon_emoji VARCHAR(16), 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES accounts (id) ON DELETE CASCADE, 
	FOREIGN KEY(pet_type_id) REFERENCES pet_types (id) ON DELETE RESTRICT
);
CREATE INDEX ix_pets_owner_id ON pets (owner_id);
CREATE INDEX ix_pets_pet_type_id ON pets (pet_type_id);

CREATE TABLE resources (
	pet_type_id UUID NOT NULL, 
	author_id UUID NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	content_type VARCHAR(20) NOT NULL, 
	media_path VARCHAR(500), 
	status VARCHAR(9) NOT NULL, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pet_type_id) REFERENCES pet_types (id) ON DELETE RESTRICT, 
	FOREIGN KEY(author_id) REFERENCES accounts (id) ON DELETE RESTRICT
);
CREATE INDEX ix_resources_author_id ON resources (author_id);
CREATE INDEX ix_resources_pet_type_id ON resources (pet_type_id);
CREATE INDEX ix_resources_status ON resources (status);

CREATE TABLE user_credentials (
	account_id UUID NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	hashed_password VARCHAR(255) NOT NULL, 
	mfa_enabled BOOLEAN NOT NULL, 
	mfa_secret VARCHAR(64), 
	failed_attempts INTEGER NOT NULL, 
	locked_until TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX ix_user_credentials_account_id ON user_credentials (account_id);
CREATE UNIQUE INDEX ix_user_credentials_email ON user_credentials (email);

CREATE TABLE chat_messages (
	chat_id UUID NOT NULL, 
	sender_id UUID NOT NULL, 
	body TEXT NOT NULL, 
	image_url TEXT, 
	sent_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(chat_id) REFERENCES chats (id) ON DELETE CASCADE, 
	FOREIGN KEY(sender_id) REFERENCES accounts (id) ON DELETE CASCADE
);
CREATE INDEX ix_chat_messages_chat_id ON chat_messages (chat_id);
CREATE INDEX ix_chat_messages_sender_id ON chat_messages (sender_id);

CREATE TABLE donation_records (
	donation_id UUID NOT NULL, 
	transaction_ref VARCHAR(120) NOT NULL, 
	provider VARCHAR(40) NOT NULL, 
	amount_cents INTEGER NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	final_status VARCHAR(20) NOT NULL, 
	processed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(donation_id) REFERENCES donations (id) ON DELETE CASCADE, 
	UNIQUE (transaction_ref)
);
CREATE UNIQUE INDEX ix_donation_records_donation_id ON donation_records (donation_id);

CREATE TABLE feedback_entries (
	feedback_id UUID NOT NULL, 
	rating INTEGER NOT NULL, 
	comment TEXT NOT NULL, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(feedback_id) REFERENCES feedback (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX ix_feedback_entries_feedback_id ON feedback_entries (feedback_id);

CREATE TABLE first_aid_resource_link (
	guidance_id UUID NOT NULL, 
	resource_id UUID NOT NULL, 
	PRIMARY KEY (guidance_id, resource_id), 
	FOREIGN KEY(guidance_id) REFERENCES first_aid_guidance (id) ON DELETE CASCADE, 
	FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
);

CREATE TABLE quizzes (
	resource_id UUID NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	passing_score INTEGER NOT NULL, 
	questions JSONB NOT NULL, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
);
CREATE INDEX ix_quizzes_resource_id ON quizzes (resource_id);

CREATE TABLE quiz_attempts (
	pet_owner_id UUID NOT NULL, 
	quiz_id UUID NOT NULL, 
	score_pct INTEGER NOT NULL, 
	passed BOOLEAN NOT NULL, 
	answers JSONB NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL DEFAULT gen_random_uuid(), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pet_owner_id) REFERENCES accounts (id) ON DELETE CASCADE, 
	FOREIGN KEY(quiz_id) REFERENCES quizzes (id) ON DELETE CASCADE
);
CREATE INDEX ix_quiz_attempts_pet_owner_id ON quiz_attempts (pet_owner_id);
CREATE INDEX ix_quiz_attempts_quiz_id ON quiz_attempts (quiz_id);


-- ---------------------------------------------------------------------
--  Domain CHECK constraints - mirror the Python enums / value ranges so
--  the database enforces the same invariants as the application layer.
-- ---------------------------------------------------------------------
alter table accounts          add constraint ck_accounts_role        check (role in ('pet_owner','veterinary_expert'));
alter table chats             add constraint ck_chats_status         check (status in ('initiated','active','closed'));
alter table inquiries         add constraint ck_inquiries_status     check (status in ('pending','responded','closed'));
alter table resources         add constraint ck_resources_status     check (status in ('draft','published'));
alter table donations         add constraint ck_donations_status     check (status in ('pending','succeeded','failed'));
alter table feedback          add constraint ck_feedback_target      check (target_type in ('resource','guidance'));
alter table feedback_entries  add constraint ck_feedback_rating      check (rating between 1 and 5);
alter table quiz_attempts     add constraint ck_quiz_attempts_score  check (score_pct between 0 and 100);


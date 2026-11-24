"""Create the Chat schema and adopt tables created by earlier application versions."""

from alembic import op

revision = "0001_chat"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS conversation_counter (
            conversation_id UUID PRIMARY KEY,
            last_seq BIGINT NOT NULL DEFAULT 0
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id UUID PRIMARY KEY,
            conversation_id UUID NOT NULL,
            uploader_id UUID NOT NULL,
            kind VARCHAR(10) NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            media_type VARCHAR(100) NOT NULL,
            byte_size BIGINT NOT NULL,
            duration_ms INT,
            file_path TEXT NOT NULL,
            bound_to_message_id UUID,
            created_at TIMESTAMPTZ NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id UUID PRIMARY KEY,
            conversation_id UUID NOT NULL,
            seq BIGINT NOT NULL,
            sender_id UUID NOT NULL,
            client_message_id UUID NOT NULL,
            content_type VARCHAR(20) NOT NULL,
            text_content TEXT,
            attachment_id UUID REFERENCES attachments(id),
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (conversation_id, seq)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_conv_seq ON messages (conversation_id, seq)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS read_states (
            conversation_id UUID NOT NULL,
            user_id UUID NOT NULL,
            last_read_seq BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (conversation_id, user_id)
        )
    """)
    # Historical messages only contain a sender UUID. Keep their previous display name.
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender_username TEXT")
    op.execute("""
        UPDATE messages SET sender_username = 'user_' || left(sender_id::text, 8)
        WHERE sender_username IS NULL
    """)
    op.execute("ALTER TABLE messages ALTER COLUMN sender_username SET NOT NULL")
    op.execute("""
        CREATE UNIQUE INDEX messages_sender_client_key ON messages (sender_id, client_message_id)
    """)


def downgrade() -> None:
    raise NotImplementedError("Restoring the pre-migration database requires a backup.")

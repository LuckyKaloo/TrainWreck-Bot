from sqlalchemy import DDL, create_engine

from mappings import Base

engine = create_engine("sqlite:///games.db", echo=True)

with engine.connect() as conn:
    _ = conn.execute(DDL("DROP TABLE IF EXISTS Card"))
    _ = conn.execute(DDL("DROP TABLE IF EXISTS Chat"))
    _ = conn.execute(DDL("DROP TABLE IF EXISTS Game"))
    _ = conn.execute(DDL("DROP TABLE IF EXISTS TeamCardJoin"))

    Base.metadata.create_all(engine)

    _ = conn.execute(
        DDL(
            """
            CREATE TRIGGER check_game_started_before_update
                BEFORE UPDATE
                ON Game
                FOR EACH ROW
                WHEN NEW.is_started = 1
            BEGIN
                SELECT CASE
                           WHEN NOT EXISTS (SELECT 1 FROM Chat WHERE Chat.game_id = NEW.game_id AND role = 'LOCATION')
                               OR NOT EXISTS (SELECT 1 FROM Chat WHERE Chat.game_id = NEW.game_id AND role = 'TEAM_1')
                               OR NOT EXISTS (SELECT 1 FROM Chat WHERE Chat.game_id = NEW.game_id AND role = 'TEAM_2')
                               OR NOT EXISTS (SELECT 1 FROM Chat WHERE Chat.game_id = NEW.game_id AND role = 'TEAM_3')
                               OR NEW.running_team_chat_id IS NULL
                               THEN RAISE(ABORT, 'Cannot start game: all required chats must exist')
                           END;
            END;
            """,
        ),
    )

    _ = conn.execute(
        DDL(
            """
            CREATE TRIGGER check_running_team_id
                BEFORE UPDATE
                ON Game
                FOR EACH ROW
                WHEN NEW.running_team_chat_id IS NOT NULL
            BEGIN
                SELECT CASE
                           WHEN NOT EXISTS (SELECT 1
                                            FROM Chat
                                            WHERE Chat.chat_id = NEW.running_team_chat_id
                                              AND Chat.role IN ('TEAM_1', 'TEAM_2', 'TEAM_3'))
                               THEN RAISE(ABORT, 'running_team_chat_id must reference a team chat')
                           END;
            END;
            """,
        ),
    )

    conn.commit()

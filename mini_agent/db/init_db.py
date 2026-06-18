from sqlalchemy import delete, text

from mini_agent.core.auth import hash_password
from mini_agent.db.session import Base, db_session, engine
from mini_agent.db.models import AppUser, Order, RefundTicket



def create_extensions() -> None:

    with engine.begin() as conn:

        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def reset_demo_data() -> None:
    with db_session() as db:
        db.execute(delete(RefundTicket))
        db.execute(delete(Order))
        db.execute(delete(AppUser))

        db.add_all([
            AppUser(
                user_id="user_001",
                username="alice",
                hashed_password=hash_password("alice123"),
                role="customer",
                disabled=False,
            ),
            AppUser(
                user_id="user_002",
                username="bob",
                hashed_password=hash_password("bob123"),
                role="customer",
                disabled=False,
            ),
            AppUser(
                user_id="admin_001",
                username="admin",
                hashed_password=hash_password("admin123"),
                role="admin",
                disabled=False,
            ),
        ])

        db.add_all([
            Order(
                order_id="A1001",
                user_id="user_001",
                status="shipped",
                carrier="DHL",
                eta="2026-05-28",
            ),
            Order(
                order_id="A1002",
                user_id="user_001",
                status="processing",
                carrier=None,
                eta=None,
            ),
            Order(
                order_id="A1003",
                user_id="user_001",
                status="delivered",
                carrier="UPS",
                eta=None,
            ),
            Order(
                order_id="B2001",
                user_id="user_002",
                status="processing",
                carrier=None,
                eta=None,
            ),
        ])


def main() -> None:
    create_extensions()
    create_tables()
    reset_demo_data()
    print("数据库表已创建，demo 用户和订单数据已初始化。")
    print("Demo 用户：")
    print("- alice / alice123")
    print("- bob / bob123")
    print("- admin / admin123")


if __name__ == "__main__":
    main()

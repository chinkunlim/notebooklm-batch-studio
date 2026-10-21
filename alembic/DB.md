# 資料庫（SQLAlchemy + Alembic + SQLite）

- 連線位置：預設是資料資料夾內的 `<DATA_DIR>/db/app.db`（`DATA_DIR` 在 `.env`，位於專案資料夾之外）；要用其他資料庫時，在 `.env` 設定 `DATABASE_URL`。
- 資料表定義：`src/<pkg>/adapters/db/models.py`；存取資料只透過 `repository.py`，回傳 domain 物件。
- 交易：一律用 `session_scope()`，成功自動 commit、錯誤自動 rollback。

改資料表的流程：

1. 修改 `models.py`。
2. 產生遷移檔（檔案開頭會有說明，請補上變更內容）：

```bash
uv run alembic revision --autogenerate -m "add price to products"
```

3. 套用到本機資料庫：

```bash
uv run alembic upgrade head
```

4. 確認模型和遷移一致（`agentctl check` 也會檢查）：

```bash
uv run alembic check
```

改用 PostgreSQL：`uv add 'psycopg[binary]'`，再把 `DATABASE_URL` 改成 `postgresql+psycopg://user@127.0.0.1:5432/dbname`。

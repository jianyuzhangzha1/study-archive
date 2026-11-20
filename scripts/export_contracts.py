"""Generate contracts from the implementation, never hand-copy schemas."""
import json
from pathlib import Path
from sqlalchemy.schema import CreateTable, CreateIndex, AddConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.ddl import sort_tables_and_constraints
from app.main import app
from app.models import Base
root=Path(__file__).resolve().parents[1]
(root/'docs'/'openapi.json').write_text(json.dumps(app.openapi(),ensure_ascii=False,indent=2))
dialect=postgresql.dialect();lines=['-- Initial schema v0.1.0; generated from app/models.py.\n-- Application supplies UUIDs and timestamps. No seed personal data.\nBEGIN;']
for table, foreign_keys in sort_tables_and_constraints(Base.metadata.tables.values()):
    if table is not None:
        lines.append(str(CreateTable(table,include_foreign_key_constraints=foreign_keys).compile(dialect=dialect))+';')
        for index in table.indexes:lines.append(str(CreateIndex(index).compile(dialect=dialect))+';')
    else:
        for fk in foreign_keys:lines.append(str(AddConstraint(fk).compile(dialect=dialect))+';')
lines.append('COMMIT;')
(root/'db'/'001_initial.sql').write_text('\n'.join(lines))
print('Generated OpenAPI and PostgreSQL DDL')

"""Improve repository taxonomy and remove untouched unsafe imported properties.

Revision ID: 20260716_15
Revises: 20260716_14
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_15"
down_revision: str | None = "20260716_14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    categories = (
        ("00000000-0000-4000-8000-000000000011", "integrated-circuits", "Микросхемы", 10),
        ("00000000-0000-4000-8000-000000000012", "semiconductors", "Полупроводники", 11),
    )
    for category_id, key, name, position in categories:
        op.execute(
            sa.text(
                "INSERT INTO categories (id,key,name,is_active,position) "
                "VALUES (CAST(:id AS uuid),:key,:name,true,:position) "
                "ON CONFLICT (key) DO UPDATE SET name=EXCLUDED.name,is_active=true,"
                "position=EXCLUDED.position"
            ).bindparams(id=category_id, key=key, name=name, position=position)
        )
    op.execute("UPDATE categories SET position=99 WHERE key='other'")
    op.execute(
        "UPDATE sources SET adapter_version='1.1.0',updated_at=now() "
        "WHERE key IN ('seeed_wiki','kicad_symbols')"
    )

    op.execute(
        """
        UPDATE components AS component
        SET primary_category_id = category.id
        FROM component_sources AS relation
        JOIN sources AS source ON source.id = relation.source_id,
             categories AS category
        WHERE category.key = CASE
            WHEN relation.source_file_path LIKE 'Sensor\\_%' ESCAPE '\\' THEN 'sensors'
            WHEN relation.source_file_path LIKE 'Display\\_%' ESCAPE '\\'
              OR relation.source_file_path LIKE 'LED%' THEN 'displays'
            WHEN relation.source_file_path LIKE 'Relay%'
              OR relation.source_file_path LIKE 'Motor%'
              OR relation.source_file_path LIKE 'Driver\\_Motor%' ESCAPE '\\' THEN 'actuators'
            WHEN relation.source_file_path LIKE 'Switch%' THEN 'input'
            WHEN relation.source_file_path LIKE 'Regulator\\_%' ESCAPE '\\' THEN 'power'
            WHEN relation.source_file_path LIKE 'Interface\\_%' ESCAPE '\\' THEN 'communication'
            WHEN relation.source_file_path LIKE 'Connector%' THEN 'prototyping'
            WHEN relation.source_file_path LIKE 'MCU\\_%' ESCAPE '\\'
              OR relation.source_file_path LIKE '74xx%'
              OR relation.source_file_path LIKE 'Timer%'
              OR relation.source_file_path LIKE 'Memory%' THEN 'integrated-circuits'
            WHEN relation.source_file_path LIKE 'Transistor\\_%' ESCAPE '\\'
              OR relation.source_file_path LIKE 'Transistor\\_Array%' ESCAPE '\\'
              OR relation.source_file_path LIKE 'Diode%' THEN 'semiconductors'
            ELSE 'other'
        END
          AND relation.component_id = component.id
          AND source.key = 'kicad_symbols'
          AND component.manual_original = false
          AND component.primary_category_id = (SELECT id FROM categories WHERE key='other')
        """
    )
    op.execute(
        """
        UPDATE components AS component
        SET primary_category_id = category.id
        FROM component_sources AS relation
        JOIN sources AS source ON source.id = relation.source_id,
             categories AS category
        WHERE category.key = CASE
            WHEN lower(component.title) ~ '(relay|motor|servo|solenoid|pump|actuator|buzzer)'
              THEN 'actuators'
            WHEN lower(component.title) ~ '(button|switch|joystick|keypad|encoder|potentiometer)'
              THEN 'input'
            WHEN lower(component.title) ~ '(display|oled|lcd|screen)' THEN 'displays'
            ELSE 'sensors'
        END
          AND relation.component_id = component.id
          AND source.key = 'seeed_wiki'
          AND component.manual_original = false
        """
    )

    op.execute(
        """
        DELETE FROM component_properties AS property
        USING components AS component, component_sources AS relation,
              sources AS source, property_definitions AS definition
        WHERE property.component_id = component.id
          AND relation.component_id = component.id
          AND source.id = relation.source_id
          AND definition.id = property.definition_id
          AND source.key = 'seeed_wiki'
          AND component.manual_original = false
          AND component.revision = 1
          AND definition.key NOT IN (
              'supply-voltage','operating-voltage','operating-current','power-consumption',
              'operating-temperature','measurement-range','accuracy','resolution','frequency',
              'dimensions','weight','interface','connector','electrical-life','actuation-force'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        "UPDATE components SET primary_category_id=(SELECT id FROM categories WHERE key='other') "
        "WHERE primary_category_id IN "
        "(SELECT id FROM categories WHERE key IN ('integrated-circuits','semiconductors'))"
    )
    op.execute("DELETE FROM categories WHERE key IN ('integrated-circuits','semiconductors')")
    op.execute("UPDATE categories SET position=9 WHERE key='other'")
    op.execute(
        "UPDATE sources SET adapter_version='1.0.0',updated_at=now() "
        "WHERE key IN ('seeed_wiki','kicad_symbols')"
    )

"""Drop the uploaded picture.

The mascots (0003) replaced it outright, so the column, the media it pointed
at and the whole upload path go together. Files already on disk under
``MEDIA_ROOT/avatars/`` are left where they are — a migration that deleted
somebody's data on the way past is not one anybody can run twice with
confidence — and are safe to remove by hand once this has shipped.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0003_player_mascot'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='player',
            name='avatar',
        ),
    ]

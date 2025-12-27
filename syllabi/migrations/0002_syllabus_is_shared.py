from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("syllabi", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="syllabus",
            name="is_shared",
            field=models.BooleanField(default=False),
        ),
    ]

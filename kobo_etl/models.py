from django.db import models


class KoboETLConfig(models.Model):
    """
    Model to store Kobo ETL configuration if needed in the future
    """
    class Meta:
        managed = False  # This is a virtual model for permissions only
        permissions = [
            ('view_etl_status', 'Can view ETL status'),
            ('run_etl', 'Can run ETL processes'),
        ]
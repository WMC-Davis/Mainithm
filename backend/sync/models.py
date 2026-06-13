from django.db import models


class MaimaiSong(models.Model):
    song_id = models.IntegerField(unique=True)
    possible_chart_types = models.CharField(max_length=16)
    title = models.CharField(max_length=512)
    chart_type = models.CharField(max_length=8)
    charts = models.JSONField(default=list)
    bpm = models.IntegerField(null=True, blank=True)
    version = models.CharField(max_length=64, blank=True)
    release_date = models.DateField(null=True, blank=True)
    aliases = models.TextField(blank=True)

    def __str__(self):
        return f'{self.title} ({self.chart_type})'


class ChunithmSong(models.Model):
    song_id = models.IntegerField(unique=True)
    category = models.CharField(max_length=64, blank=True)
    title = models.CharField(max_length=512)
    artist = models.CharField(max_length=256, blank=True)
    charts = models.JSONField(default=list)
    bpm = models.IntegerField(null=True, blank=True)
    version = models.CharField(max_length=64, blank=True)
    aliases = models.TextField(blank=True)

    def __str__(self):
        return self.title


class DelayDifference(models.Model):
    maimai_song = models.ForeignKey(MaimaiSong, on_delete=models.CASCADE)
    chunithm_song = models.ForeignKey(ChunithmSong, on_delete=models.CASCADE)
    delay_ms = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['maimai_song', 'chunithm_song'],
                name='unique_delay_pair',
            ),
        ]

    def __str__(self):
        return f'{self.maimai_song.title} <-> {self.chunithm_song.title}: {self.delay_ms}ms'


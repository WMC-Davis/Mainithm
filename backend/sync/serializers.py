from rest_framework import serializers

from .models import MaimaiSong, ChunithmSong, DelayDifference


class MaimaiSongSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaimaiSong
        exclude = ['id']


class ChunithmSongSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChunithmSong
        exclude = ['id']


class DelayDifferenceSerializer(serializers.ModelSerializer):

    maimai_song = serializers.SlugRelatedField(
        slug_field='song_id', queryset=MaimaiSong.objects.all()
    )
    chunithm_song = serializers.SlugRelatedField(
        slug_field='song_id', queryset=ChunithmSong.objects.all()
    )

    class Meta:
        model = DelayDifference
        fields = '__all__'


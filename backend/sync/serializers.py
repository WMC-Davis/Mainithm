from rest_framework import serializers

from .models import MaimaiSong, ChunithmSong, DelayDifference


class MaimaiSongSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaimaiSong
        fields = '__all__'


class ChunithmSongSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChunithmSong
        fields = '__all__'


class DelayDifferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DelayDifference
        fields = '__all__'


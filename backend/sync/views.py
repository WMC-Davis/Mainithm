from rest_framework.decorators import api_view
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from .models import MaimaiSong, ChunithmSong, DelayDifference
from .serializers import MaimaiSongSerializer, ChunithmSongSerializer, DelayDifferenceSerializer


@api_view(['GET'])
def ping(request):
    return Response({'status': 'ok'})


class MaimaiSongViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    queryset = MaimaiSong.objects.all()
    serializer_class = MaimaiSongSerializer
    lookup_field = 'song_id'


class ChunithmSongViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    queryset = ChunithmSong.objects.all()
    serializer_class = ChunithmSongSerializer
    lookup_field = 'song_id'


class DelayDifferenceViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    queryset = DelayDifference.objects.select_related('maimai_song', 'chunithm_song')
    serializer_class = DelayDifferenceSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        maimai_song_id = self.request.query_params.get('maimai_song')
        chunithm_song_id = self.request.query_params.get('chunithm_song')
        if maimai_song_id:
            queryset = queryset.filter(maimai_song__song_id=maimai_song_id)
        if chunithm_song_id:
            queryset = queryset.filter(chunithm_song__song_id=chunithm_song_id)
        return queryset


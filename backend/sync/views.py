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


class ChunithmSongViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    queryset = ChunithmSong.objects.all()
    serializer_class = ChunithmSongSerializer


class DelayDifferenceViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    queryset = DelayDifference.objects.all()
    serializer_class = DelayDifferenceSerializer

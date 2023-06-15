# # class TagViewSet(viewsets.ModelViewSet):
# #     """
# #     API endpoint that allows users to be viewed or edited.
# #     - list (GET)
# #     - create (POST)
# #     - retrieve (GET id)
# #     - update (PUT id)
# #     - partial update (PATCH id)
# #     - destroy (DELETE id)
# #     """
# #     queryset = ArtifactTag.objects.all().order_by('tag')
# #     serializer_class = TagSerializer
# #     permission_classes = [permissions.AllowAny]
# #
# #     def list(self, request, *args, **kwargs):
# #         """
# #         list (GET)
# #         """
# #         return super().list(request, *args, **kwargs)
# #
# #     def create(self, request, *args, **kwargs):
# #         """
# #         create (POST)
# #         """
# #         return super().create(request, *args, **kwargs)
# #
# #     def retrieve(self, request, *args, **kwargs):
# #         """
# #         retrieve (GET {int:pk})
# #         """
# #         return super().retrieve(request, *args, **kwargs)
# #
# #     def update(self, request, *args, **kwargs):
# #         """
# #         update (PUT {int:pk})
# #         """
# #         return super().update(request, *args, **kwargs)
# #
# #     def partial_update(self, request, *args, **kwargs):
# #         """
# #         partial_update (PATCH {int:pk})
# #         """
# #         return super().partial_update(request, *args, **kwargs)
# #
# #     def destroy(self, request, *args, **kwargs):
# #         """
# #         destroy (DELETE {int:pk})
# #         """
# #         return super().destroy(request, *args, **kwargs)

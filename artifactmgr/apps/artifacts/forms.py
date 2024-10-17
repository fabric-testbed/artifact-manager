from django import forms
from django.forms import CheckboxSelectMultiple

from artifactmgr.apps.artifacts.models import ApiUser, Artifact, ArtifactAuthor, ArtifactTag


class ArtifactForm(forms.ModelForm):
    """
    {
        "authors": [
            "string"
        ],
        "description_long": "string",
        "description_short": "string",
        "project_uuid": "string",
        "tags": [
            "string"
        ],
        "title": "string",
        "visibility": "author"
    }
    """
    required_css_class = 'required'

    title = forms.CharField(
        widget=forms.TextInput(attrs={'size': 60}),
        required=True,
        label='Title',
    )

    description_short = forms.CharField(
        widget=forms.TextInput(attrs={'size': 60}),
        required=True,
        label='Short Description',
    )

    description_long = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 1, 'cols': 20}),
        required=False,
        label='Long Description',
    )

    show_project = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': 'checkbox'}),
        required=False,
        initial=True,
        label='Show Project - checked=True (uncheck for Double-Blind reference)',
    )

    project_uuid = forms.CharField(
        widget=forms.TextInput(attrs={'size': 60}),
        required=False,
        label='Project (by UUID) - required if Visibility is set as "Project"',
    )

    show_authors = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': 'checkbox'}),
        required=False,
        initial=True,
        label='Show Authors - checked=True (uncheck for Double-Blind reference)',
    )

    author_1 = forms.CharField(required=False)
    author_2 = forms.CharField(required=False)
    author_3 = forms.CharField(required=False)
    author_4 = forms.CharField(required=False)
    author_5 = forms.CharField(required=False)
    author_6 = forms.CharField(required=False)
    author_7 = forms.CharField(required=False)
    author_8 = forms.CharField(required=False)
    author_9 = forms.CharField(required=False)
    author_10 = forms.CharField(required=False)
    author_11 = forms.CharField(required=False)
    author_12 = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        authors = kwargs.pop('authors', [])
        api_user_uuid = kwargs.pop('api_user', None)
        super().__init__(*args, **kwargs)
        api_user = ApiUser.objects.filter(uuid=api_user_uuid).first()

        if api_user and api_user.is_artifact_manager_admin:
            available_tags = [(t.tag, t.tag)
                              for t in ArtifactTag.objects.all().order_by('tag')]
        else:
            available_tags = [(t.tag, t.tag)
                              for t in ArtifactTag.objects.filter(
                    restricted=False
                ).order_by('tag')]

        self.fields['tags'] = forms.MultipleChoiceField(
            widget=CheckboxSelectMultiple,
            choices=available_tags,
            required=False,
            label='Tags',
        )

        for i in range(len(authors)):
            field_name = 'author_%s' % (i + 1,)
            self.fields[field_name] = forms.CharField(required=False)
            try:
                a = ArtifactAuthor.objects.filter(uuid=authors[i]).first()
                self.initial[field_name] = '{0}: {1}'.format(a.uuid, a)
            except IndexError:
                self.initial[field_name] = ''

    def clean(self):
        authors = []
        i = 1
        field_name = 'author_%s' % (i,)
        while i <= 12:
            author = str(self.cleaned_data[field_name]).split(':')[0]
            if author and author not in authors:
                authors.append(author)
            i += 1
            field_name = 'author_%s' % (i,)

        self.cleaned_data['authors'] = authors

    class Meta:
        model = Artifact
        fields = ['title', 'description_short', 'description_long',
                  'visibility', 'show_project', 'project_uuid', 'show_authors', 'tags']

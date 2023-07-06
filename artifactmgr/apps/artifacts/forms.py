from django import forms
from django.forms import CheckboxSelectMultiple

from artifactmgr.apps.artifacts.models import Artifact, ArtifactTag


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

    project_uuid = forms.CharField(
        widget=forms.TextInput(attrs={'size': 60}),
        required=False,
        label='Project (by UUID) - required if Visibility = Project',
    )

    # author_count = forms.ChoiceField(
    #     choices=[(1, 'One'), (2, 'Two'), (3, 'Three'), (4, 'Four'), (5, 'Five'), (6, 'Six'), (7, 'Seven'),
    #              (8, 'Eight'), (9, 'Nine'), (10, 'Ten'), (11, 'Eleven'), (12, 'Twelve')],
    #     required=False,
    #     initial=(4, 'Four')
    # )

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
        print(kwargs)
        authors = kwargs.pop('authors', [])
        super().__init__(*args, **kwargs)

        available_tags = [(t.tag, t.tag) for t in ArtifactTag.objects.all().order_by('tag')]

        self.fields['tags'] = forms.MultipleChoiceField(
            widget=CheckboxSelectMultiple,
            choices=available_tags,
            required=False,
            label='Tags',
        )

        for i in range(len(authors)):
            field_name = 'author_%s' % (i+1,)
            self.fields[field_name] = forms.CharField(required=False)
            try:
                self.initial[field_name] = authors[i]
            except IndexError:
                self.initial[field_name] = ''

    def clean(self):
        authors = []
        i = 1
        field_name = 'author_%s' % (i,)
        while self.cleaned_data.get(field_name):
            author = self.cleaned_data[field_name]
            if author in authors:
                self.add_error(field_name, 'Duplicate')
            else:
                authors.append(author)
            i += 1
            field_name = 'author_%s' % (i,)

        self.cleaned_data['authors'] = authors

    class Meta:
        model = Artifact
        fields = ['title', 'description_short', 'description_long', 'visibility', 'project_uuid', 'tags']

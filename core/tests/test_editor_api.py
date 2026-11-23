import base64
import io
import re
import uuid

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image as PILImage
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.util import Inches
from rest_framework import status
from rest_framework.test import APIClient

from core.models import Design, DesignPage, Element, Symbol, User
from core.models.editor_image import EditorImage
from core.services.file_import import import_file_into_design
from uploader.models import Image as UploaderImage
from uploader.views import ImageUploadViewSet

EXPECTED_PAGE_COUNT = 2
EXPECTED_IMAGES_IN_DESIGNS = 2
EXPECTED_ROTATION = 133.5
BALLOON_ROTATION = 30


def example_png():
    stream = io.BytesIO()
    PILImage.new('RGB', (20, 20), (255, 100, 0)).save(stream, 'PNG')
    return stream.getvalue()


class MediaLibraryTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email='alice@example.com', password='secret')
        self.bob = User.objects.create_user(email='bob@example.com', password='secret')
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def upload(self):
        return self.client.post(
            '/api/editor-images/',
            {'file': SimpleUploadedFile('figura.png', example_png(), content_type='image/png')},
            format='multipart',
        )

    def test_same_owner_reuses_content_and_other_owner_cannot_read_it(self):
        first = self.upload()
        assert first.status_code == status.HTTP_201_CREATED, first.data
        assert not first.data['reused']
        assert '/api/editor-images/' in first.data['url']
        second = self.upload()
        assert second.status_code == status.HTTP_200_OK, second.data
        assert second.data['reused']
        assert first.data['id'] == second.data['id']
        assert EditorImage.objects.filter(owner=self.alice).count() == 1

        photo = EditorImage.objects.get(pk=first.data['id'])
        assert photo.file
        assert not str(photo.file.path).startswith(str(settings.MEDIA_ROOT))
        own_file = self.client.get(first.data['url'])
        assert own_file.status_code == status.HTTP_200_OK

        self.client.force_authenticate(self.bob)
        assert self.client.get('/api/editor-images/').data['results'] == []
        assert self.client.get(first.data['url']).status_code == status.HTTP_404_NOT_FOUND
        assert self.client.get(f'/api/editor-images/{first.data["id"]}/').status_code == status.HTTP_404_NOT_FOUND
        other = self.upload()
        assert other.status_code == status.HTTP_201_CREATED
        assert EditorImage.objects.count() == EXPECTED_IMAGES_IN_DESIGNS

    def test_editor_assets_do_not_change_uploader(self):
        assert UploaderImage.objects.count() == 0
        assert ImageUploadViewSet is not None
        assert not hasattr(UploaderImage, 'owner')

    def test_unauthenticated_cannot_list_images(self):
        anonymous = APIClient()
        assert anonymous.get('/api/editor-images/').status_code == status.HTTP_401_UNAUTHORIZED
        assert anonymous.get('/api/editor-images/999/content/').status_code == status.HTTP_401_UNAUTHORIZED

    def test_reject_invalid_upload(self):
        bad = SimpleUploadedFile('fake.png', b'not an image', content_type='image/png')
        response = self.client.post('/api/editor-images/', {'file': bad}, format='multipart')
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class EditorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='editor@example.com', password='secret')
        self.other = User.objects.create_user(email='other@example.com', password='secret')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.design = Design.objects.create(name='Slides', created_by=self.user)
        self.page = DesignPage.objects.create(design=self.design, page_order=0)
        self.second = DesignPage.objects.create(design=self.design, page_order=1)

    def test_rotation_symbol_and_page_only_response(self):
        symbol = Symbol.objects.get(key='balao')
        element = {
            'client_id': str(uuid.uuid4()),
            'type': 'symbol',
            'symbol': symbol.id,
            'content': '',
            'posicao_x': 15,
            'posicao_y': 23,
            'width': 200,
            'heigth': 190,
            'color': '#ff5700',
            'rotation': 133.5,
            'layer_order': 0,
        }
        url = f'/api/designs/{self.design.id}/save-elements/'
        response = self.client.patch(url, {'page_id': self.page.id, 'elements': [element]}, format='json')
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data['page_id'] == self.page.id
        assert 'pages' not in response.data
        assert response.data['elements'][0]['rotation'] == EXPECTED_ROTATION
        assert response.data['elements'][0]['symbol_data']['name'] == 'Balão de fala'
        assert Element.objects.get(page=self.page).symbol_id == symbol.id
        assert Element.objects.filter(page=self.second).count() == 0

        summary = self.client.get(f'/api/designs/{self.design.id}/?summary=1')
        assert summary.status_code == status.HTTP_200_OK
        assert 'elements' not in summary.data['pages'][0]
        detailed = self.client.get(f'/api/designs/{self.design.id}/page/?page_id={self.page.id}')
        assert detailed.data['elements'][0]['rotation'] == EXPECTED_ROTATION

    def test_symbol_library_is_shared_and_private_designs_are_not(self):
        public = self.client.get('/api/symbols/')
        assert public.status_code == status.HTTP_200_OK
        assert any(s['key'] == 'balao' for s in public.data)
        created = self.client.post(
            '/api/symbols/',
            {'name': 'Meu símbolo', 'path_data': 'M 2 2 L 80 2 L 40 80 Z'},
            format='json',
        )
        assert created.status_code == status.HTTP_201_CREATED, created.data
        self.client.force_authenticate(self.other)
        assert any(symbol['id'] == created.data['id'] for symbol in self.client.get('/api/symbols/').data)
        assert self.client.get(f'/api/designs/{self.design.id}/').status_code == status.HTTP_404_NOT_FOUND
        response = self.client.get(f'/api/designs/{self.design.id}/page/?page_id={self.page.id}')
        assert response.status_code == status.HTTP_404_NOT_FOUND


class PowerPointImportTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='pptx@example.com', password='secret')

    def build_presentation(self):
        presentation = Presentation()
        png = example_png()
        for index in range(2):
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            slide.shapes.add_picture(io.BytesIO(png), Inches(1), Inches(1))
            baloon = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.BALLOON, Inches(2), Inches(2), Inches(2), Inches(1))
            baloon.rotation = 30 + index
            baloon.fill.solid()
            baloon.fill.fore_color.rgb = RGBColor(10, 20, 30)
        stream = io.BytesIO()
        presentation.save(stream)
        return stream.getvalue()

    def test_same_images_reuse_bytes_and_balloons_are_vectors(self):
        raw = self.build_presentation()
        for index in range(2):
            design = Design.objects.create(name=f'PPTX {index}', created_by=self.owner)
            file = SimpleUploadedFile(f'copy-{index}.pptx', raw)
            import_file_into_design(file, design, self.owner)
            assert design.pages.count() == EXPECTED_PAGE_COUNT
            symbol = design.elements.filter(type='symbol').first()
            assert symbol is not None
            assert symbol.symbol.key == 'balao'
            assert symbol.rotation == BALLOON_ROTATION
            assert design.elements.filter(type='image').count() == EXPECTED_IMAGES_IN_DESIGNS
        assert EditorImage.objects.filter(owner=self.owner).count() == 1


class DataUrlMigrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='base64@example.com', password='secret')
        self.guest = User.objects.create_user(email='guest@example.com', password='secret')
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.design = Design.objects.create(created_by=self.owner)
        self.page = DesignPage.objects.create(design=self.design, page_order=0)

    def send(self, content, user=None):
        if user:
            self.client.force_authenticate(user)
        return self.client.patch(
            f'/api/designs/{self.design.id}/save-elements/',
            {
                'page_id': self.page.id,
                'elements': [
                    {
                        'client_id': str(uuid.uuid4()),
                        'type': 'image',
                        'content': content,
                        'posicao_x': 1,
                        'posicao_y': 2,
                        'width': 20,
                        'heigth': 20,
                    }
                ],
            },
            format='json',
        )

    def test_base64_legacy_element_becomes_private_file(self):
        raw = 'data:image/png;base64,' + base64.b64encode(example_png()).decode()
        response = self.send(raw)
        assert response.status_code == status.HTTP_200_OK, response.data
        assert EditorImage.objects.count() == 1
        url = response.data['elements'][0]['content']
        assert re.search(r'^/api/editor-images/\d+/content/$', url)
        assert not Element.objects.get(design=self.design).content.startswith('data:')
        # A referência privada não pode ser anexada à conta de outro usuário.
        other_design = Design.objects.create(created_by=self.guest)
        other_page = DesignPage.objects.create(design=other_design)
        self.client.force_authenticate(self.guest)
        response = self.client.patch(
            f'/api/designs/{other_design.id}/save-elements/',
            {
                'page_id': other_page.id,
                'elements': [
                    {
                        'client_id': str(uuid.uuid4()),
                        'type': 'image',
                        'content': url,
                        'posicao_x': 0,
                        'posicao_y': 0,
                        'width': 10,
                        'heigth': 10,
                    }
                ],
            },
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

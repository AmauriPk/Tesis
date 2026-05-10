"""
Tests para yolo_model_service.py

Pruebas unitarias sin descargar modelos YOLO reales.
"""
import os
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch

from src.services.yolo_model_service import (
    get_torch_device,
    resolve_yolo_model_path,
    load_yolo_model,
)


class TestGetTorchDevice(unittest.TestCase):
    """Tests para get_torch_device."""

    def test_returns_cpu_when_torch_is_none(self):
        """Si torch_module es None, debe lanzar RuntimeError."""
        with self.assertRaises(RuntimeError):
            get_torch_device(torch_module=None)

    def test_returns_cpu_when_cuda_not_available(self):
        """Si torch no tiene cuda, retorna 'cpu'."""
        mock_torch = Mock()
        mock_torch.cuda = None  # No tiene cuda

        device = get_torch_device(torch_module=mock_torch)
        self.assertEqual(device, "cpu")

    def test_returns_cpu_when_cuda_not_available_explicitly(self):
        """Si torch.cuda.is_available() es False, retorna 'cpu'."""
        mock_torch = Mock()
        mock_torch.cuda = Mock()
        mock_torch.cuda.is_available = Mock(return_value=False)

        device = get_torch_device(torch_module=mock_torch)
        self.assertEqual(device, "cpu")

    def test_returns_cuda_0_when_available(self):
        """Si torch.cuda.is_available() es True, retorna 'cuda:0'."""
        mock_torch = Mock()
        mock_torch.cuda = Mock()
        mock_torch.cuda.is_available = Mock(return_value=True)

        device = get_torch_device(torch_module=mock_torch)
        self.assertEqual(device, "cuda:0")


class TestResolveYoloModelPath(unittest.TestCase):
    """Tests para resolve_yolo_model_path."""

    def test_returns_configured_path_if_exists(self):
        """Si YOLO_CONFIG['model_path'] existe, debe retornarla."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_file = os.path.join(tmpdir, "custom_model.pt")
            # Crear archivo temporal
            open(model_file, "w").close()

            yolo_config = {"model_path": model_file}
            result = resolve_yolo_model_path(yolo_config)

            self.assertEqual(result, model_file)

    def test_returns_fallback_if_path_missing(self):
        """Si YOLO_CONFIG['model_path'] no existe, retorna fallback."""
        yolo_config = {"model_path": "/nonexistent/model.pt"}

        result = resolve_yolo_model_path(yolo_config, fallback="yolo26s.pt")

        self.assertEqual(result, "yolo26s.pt")

    def test_returns_fallback_if_config_empty(self):
        """Si YOLO_CONFIG está vacía, retorna fallback."""
        yolo_config = {}

        result = resolve_yolo_model_path(yolo_config, fallback="yolo26s.pt")

        self.assertEqual(result, "yolo26s.pt")

    def test_returns_fallback_if_config_whitespace(self):
        """Si YOLO_CONFIG['model_path'] es solo espacios, retorna fallback."""
        yolo_config = {"model_path": "   "}

        result = resolve_yolo_model_path(yolo_config, fallback="yolo26s.pt")

        self.assertEqual(result, "yolo26s.pt")

    def test_custom_fallback(self):
        """Se puede especificar un fallback personalizado."""
        yolo_config = {"model_path": "/nonexistent/model.pt"}

        result = resolve_yolo_model_path(yolo_config, fallback="yolo26n.pt")

        self.assertEqual(result, "yolo26n.pt")


class TestLoadYoloModel(unittest.TestCase):
    """Tests para load_yolo_model."""

    @patch("src.services.yolo_model_service.torch", None)
    def test_returns_none_if_torch_unavailable(self):
        """Si torch no está disponible, retorna None."""
        yolo_config = {}
        result = load_yolo_model(yolo_config)
        self.assertIsNone(result)

    @patch("src.services.yolo_model_service.YOLO", None)
    def test_returns_none_if_yolo_unavailable(self):
        """Si YOLO no está disponible, retorna None."""
        mock_torch = Mock()
        mock_torch.cuda = None

        with patch("src.services.yolo_model_service.torch", mock_torch):
            yolo_config = {}
            result = load_yolo_model(yolo_config)
            self.assertIsNone(result)

    @patch("src.services.yolo_model_service.YOLO")
    @patch("src.services.yolo_model_service.torch")
    def test_returns_model_on_success(self, mock_torch, mock_yolo_class):
        """Si carga exitosa, retorna modelo instanciado."""
        # Setup
        mock_torch.cuda = Mock()
        mock_torch.cuda.is_available = Mock(return_value=False)

        mock_model = MagicMock()
        mock_yolo_class.return_value = mock_model

        with tempfile.TemporaryDirectory() as tmpdir:
            model_file = os.path.join(tmpdir, "model.pt")
            open(model_file, "w").close()

            yolo_config = {"model_path": model_file}

            result = load_yolo_model(yolo_config)

            # Assertions
            self.assertEqual(result, mock_model)
            mock_yolo_class.assert_called_once_with(model_file)
            mock_model.to.assert_called_once_with("cpu")

    @patch("src.services.yolo_model_service.YOLO")
    @patch("src.services.yolo_model_service.torch")
    def test_moves_model_to_cuda_if_available(self, mock_torch, mock_yolo_class):
        """Si CUDA disponible, mueve modelo a cuda:0."""
        # Setup
        mock_torch.cuda = Mock()
        mock_torch.cuda.is_available = Mock(return_value=True)

        mock_model = MagicMock()
        mock_yolo_class.return_value = mock_model

        with tempfile.TemporaryDirectory() as tmpdir:
            model_file = os.path.join(tmpdir, "model.pt")
            open(model_file, "w").close()

            yolo_config = {"model_path": model_file}

            result = load_yolo_model(yolo_config)

            # Assertions
            self.assertEqual(result, mock_model)
            mock_model.to.assert_called_once_with("cuda:0")

    @patch("src.services.yolo_model_service.YOLO")
    @patch("src.services.yolo_model_service.torch")
    def test_uses_fallback_if_model_path_missing(self, mock_torch, mock_yolo_class):
        """Si YOLO_CONFIG['model_path'] no existe, usa fallback."""
        # Setup
        mock_torch.cuda = Mock()
        mock_torch.cuda.is_available = Mock(return_value=False)

        mock_model = MagicMock()
        mock_yolo_class.return_value = mock_model

        yolo_config = {"model_path": "/nonexistent/model.pt"}

        result = load_yolo_model(yolo_config)

        # Assertions
        self.assertEqual(result, mock_model)
        mock_yolo_class.assert_called_once_with("yolo26s.pt")

    @patch("src.services.yolo_model_service.YOLO")
    @patch("src.services.yolo_model_service.torch")
    def test_returns_none_on_yolo_exception(self, mock_torch, mock_yolo_class):
        """Si YOLO lanza excepción, retorna None."""
        # Setup
        mock_torch.cuda = Mock()
        mock_torch.cuda.is_available = Mock(return_value=False)

        mock_yolo_class.side_effect = RuntimeError("Model not found")

        yolo_config = {}

        result = load_yolo_model(yolo_config)

        # Assertions
        self.assertIsNone(result)

    @patch("src.services.yolo_model_service.YOLO")
    @patch("src.services.yolo_model_service.torch")
    def test_returns_none_on_model_to_device_exception(self, mock_torch, mock_yolo_class):
        """Si model.to(device) lanza excepción, retorna None."""
        # Setup
        mock_torch.cuda = Mock()
        mock_torch.cuda.is_available = Mock(return_value=False)

        mock_model = MagicMock()
        mock_model.to.side_effect = RuntimeError("CUDA error")
        mock_yolo_class.return_value = mock_model

        with tempfile.TemporaryDirectory() as tmpdir:
            model_file = os.path.join(tmpdir, "model.pt")
            open(model_file, "w").close()

            yolo_config = {"model_path": model_file}

            result = load_yolo_model(yolo_config)

            # Assertions
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

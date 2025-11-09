"""
Local SigLIP embeddings for fashion product images.
Uses google/siglip-large-patch16-384 model (1024 dimensions).
"""

import os
import logging
import requests
from PIL import Image
from io import BytesIO
import torch
from transformers import SiglipProcessor, SiglipModel
from typing import Optional, List
import numpy as np

logger = logging.getLogger(__name__)

class SigLIPEmbeddings:
    def __init__(self, model_name: str = "google/siglip-large-patch16-384"):
        self.model_name = model_name
        self.processor = None
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Using device: {self.device}")

    def _load_model(self):
        """Load the SigLIP model and processor."""
        if self.model is None:
            logger.info(f"Loading SigLIP model: {self.model_name}")
            try:
                self.processor = SiglipProcessor.from_pretrained(self.model_name)
                self.model = SiglipModel.from_pretrained(self.model_name)
                self.model.to(self.device)
                self.model.eval()
                logger.info("SigLIP model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load SigLIP model: {e}")
                raise

    def get_image_embedding(self, image_url: str, max_retries: int = 3) -> Optional[List[float]]:
        """
        Generate embedding for a single image URL.

        Args:
            image_url: URL of the image
            max_retries: Maximum number of download retries

        Returns:
            List of 1024 float values representing the image embedding, or None if failed
        """
        if self.model is None:
            self._load_model()

        # Download image
        image = self._download_image(image_url, max_retries)
        if image is None:
            return None

        try:
            # Process image
            inputs = self.processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs)
                # Use vision model output (image embeddings)
                embeddings = outputs.vision_model_output.pooler_output

                # Normalize the embedding
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

                # Convert to list
                embedding_list = embeddings.cpu().numpy().flatten().tolist()

            logger.debug(f"Generated embedding for {image_url}: dimension {len(embedding_list)}")
            return embedding_list

        except Exception as e:
            logger.error(f"Failed to generate embedding for {image_url}: {e}")
            return None

    def get_batch_embeddings(self, image_urls: List[str], batch_size: int = 8) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple images in batches.

        Args:
            image_urls: List of image URLs
            batch_size: Number of images to process in each batch

        Returns:
            List of embeddings (or None for failed images)
        """
        if self.model is None:
            self._load_model()

        results = []

        for i in range(0, len(image_urls), batch_size):
            batch_urls = image_urls[i:i + batch_size]
            batch_images = []

            # Download images for this batch
            for url in batch_urls:
                image = self._download_image(url)
                if image is not None:
                    batch_images.append(image)
                else:
                    batch_images.append(None)

            # Process valid images in batch
            valid_images = [img for img in batch_images if img is not None]
            valid_indices = [j for j, img in enumerate(batch_images) if img is not None]

            if valid_images:
                try:
                    # For SigLIP, we need to provide both images and text inputs
                    # Use empty text or a generic text prompt
                    text_inputs = [""] * len(valid_images)  # Empty text for image-only embeddings

                    inputs = self.processor(
                        text=text_inputs,
                        images=valid_images,
                        return_tensors="pt",
                        padding=True
                    )
                    inputs = {k: v.to(self.device) for k, v in inputs.items()}

                    with torch.no_grad():
                        outputs = self.model(**inputs)
                        # Get image embeddings from vision model
                        image_embeddings = outputs.vision_model_output.pooler_output
                        image_embeddings = torch.nn.functional.normalize(image_embeddings, p=2, dim=1)

                        # Convert to list of lists
                        batch_embeddings = image_embeddings.cpu().numpy().tolist()

                    # Map back to original positions
                    batch_results = [None] * len(batch_urls)
                    for idx, embedding in zip(valid_indices, batch_embeddings):
                        batch_results[idx] = embedding

                    results.extend(batch_results)

                except Exception as e:
                    logger.error(f"Failed to process batch: {e}")
                    # Log more details for debugging
                    logger.error(f"Batch URLs: {batch_urls}")
                    logger.error(f"Valid images count: {len(valid_images)}")
                    results.extend([None] * len(batch_urls))
            else:
                results.extend([None] * len(batch_urls))

        return results

    def _download_image(self, url: str, max_retries: int = 3) -> Optional[Image.Image]:
        """
        Download and preprocess image.

        Args:
            url: Image URL
            max_retries: Maximum download attempts

        Returns:
            PIL Image or None if failed
        """
        for attempt in range(max_retries):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()

                image = Image.open(BytesIO(response.content))

                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')

                return image

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Failed to download image after {max_retries} attempts: {url}")
                    return None

        return None


# Global instance for reuse
_embeddings_instance = None

def get_image_embedding(image_url: str) -> Optional[List[float]]:
    """
    Convenience function to get embedding for a single image.

    Args:
        image_url: URL of the image

    Returns:
        List of 1024 float values or None if failed
    """
    global _embeddings_instance
    if _embeddings_instance is None:
        model_name = os.getenv('EMBEDDINGS_MODEL', 'google/siglip-large-patch16-384')
        _embeddings_instance = SigLIPEmbeddings(model_name)

    return _embeddings_instance.get_image_embedding(image_url)


def get_batch_embeddings(image_urls: List[str], batch_size: int = 8) -> List[Optional[List[float]]]:
    """
    Convenience function to get embeddings for multiple images.

    Args:
        image_urls: List of image URLs
        batch_size: Batch size for processing

    Returns:
        List of embeddings (or None for failed images)
    """
    global _embeddings_instance
    if _embeddings_instance is None:
        model_name = os.getenv('EMBEDDINGS_MODEL', 'google/siglip-large-patch16-384')
        _embeddings_instance = SigLIPEmbeddings(model_name)

    return _embeddings_instance.get_batch_embeddings(image_urls, batch_size)


if __name__ == "__main__":
    # Test the embeddings
    test_url = 'https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=400'

    print("Testing SigLIP embeddings...")
    embedding = get_image_embedding(test_url)

    if embedding:
        print(f"✅ Success! Embedding dimension: {len(embedding)}")
        print(f"First 5 values: {embedding[:5]}")
    else:
        print("❌ Failed to generate embedding")

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class Noticia(BaseModel):
    id: int
    titulo: str
    fuente: str
    link_original: str
    fecha: Optional[datetime]
    imagen_url: Optional[str]
    resumen_ia: Optional[str]
    categorias: List[str]


class RespuestaNoticias(BaseModel):
    noticias: List[Noticia]
    siguiente_cursor: Optional[int]
    hay_mas: bool
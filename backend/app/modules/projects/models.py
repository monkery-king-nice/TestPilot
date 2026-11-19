"""Alpha v1 public request/response contracts."""

from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProjectInput(InputModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("项目名不能为空")
        return value.strip()


class Project(BaseModel):
    id: str
    name: str


class RequirementInput(InputModel):
    text: str = Field(min_length=1, max_length=16000)

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("需求正文不能为空")
        return value  # Preserve source text exactly for Agent quote validation.


class DocumentPreviewInput(InputModel):
    path: str = Field(min_length=1, max_length=512)
    start: int = Field(default=0, ge=0)
    end: int | None = Field(default=None, gt=0)


class RequirementSource(InputModel):
    import_id: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=512)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class RequirementCreateInput(RequirementInput):
    source: RequirementSource | None = None


class Requirement(BaseModel):
    id: str
    text: str
    version: int
    source: RequirementSource | None = None


class ConfirmImportEndpoints(InputModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=256)


class EndpointInput(InputModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    path: str = Field(min_length=1, max_length=2048)

    @field_validator("method", mode="before")
    @classmethod
    def uppercase_method(cls, value):
        return value.upper() if isinstance(value, str) else value

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        # Check decoded forms as well: encoded slashes must not become a host.
        decoded = value
        for _ in range(3):
            parsed = urlsplit(decoded)
            if (
                not decoded.startswith("/")
                or decoded.startswith("//")
                or parsed.scheme
                or parsed.netloc
                or "#" in decoded
                or "\\" in decoded
                or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in decoded)
                or ".." in parsed.path.split("/")
            ):
                raise ValueError("接口必须使用安全的相对路径")
            following = unquote(decoded)
            if following == decoded:
                return value
            decoded = following
        raise ValueError("接口路径编码层数过多")


class Endpoint(BaseModel):
    id: str
    method: str
    path: str
    version: int


class EnvironmentSecrets(InputModel):
    username: SecretStr
    password: SecretStr

    @field_validator("username", "password")
    @classmethod
    def valid_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip() or len(value.get_secret_value()) > 4096:
            raise ValueError("环境字段不能为空且不能超过4096字符")
        return value


class EnvironmentInput(InputModel):
    target: Literal["demo", "local"]
    service_id: str | None = Field(default=None, max_length=100)
    base_url: str | None = Field(default=None, max_length=2048)
    secrets: EnvironmentSecrets

    @model_validator(mode="after")
    def valid_target(self):
        if self.target == "demo":
            if self.service_id is not None or self.base_url is not None:
                raise ValueError("演示环境不接受自定义服务标识或地址")
            return self
        if not self.service_id or not self.service_id.strip():
            raise ValueError("本地测试服务必须提供明确的服务标识")
        self.service_id = self.service_id.strip()
        if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in self.service_id):
            raise ValueError("本地测试服务标识不能包含空白或控制字符")
        if not self.base_url or any(
            char.isspace() or ord(char) < 32 or ord(char) == 127 for char in self.base_url
        ):
            raise ValueError("本地测试服务地址不能为空或包含空白或控制字符")
        try:
            parsed = urlsplit(self.base_url)
            port = parsed.port
        except ValueError as error:
            raise ValueError("本地测试服务地址或端口无效") from error
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("本地测试服务仅允许带明确端口的回环 HTTP(S) 根地址")
        self.base_url = self.base_url.rstrip("/")
        return self


class EnvironmentView(BaseModel):
    target: Literal["demo", "local"] = "demo"
    service_id: str | None = None
    base_url: str | None = None
    environment_version: int | None = None
    configured_keys: list[str]

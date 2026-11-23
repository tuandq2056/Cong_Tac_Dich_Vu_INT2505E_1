# Công Tác Dịch Vụ — INT2505E_1

Kho lưu trữ bài tập và đồ án môn học Kiến trúc Hướng Dịch vụ (SOA) - INT2505E_1.

## Cấu trúc thư mục

* **[`task-api/`](./task-api)**: Bài tập thực hành Bookstore REST API & Swagger UI.
* **[`webchat/`](./webchat)**: Đồ án lớn hệ thống WebChat thời gian thực kiến trúc SOA (FastAPI microservices + React/TypeScript frontend).
  * Ranh giới 3 dịch vụ: `Identity` (tài khoản & token), `Social` (bạn bè & hội thoại), `Chat` (tin nhắn, tệp & mốc đọc).
  * Hợp đồng giao tiếp: [`webchat/contracts/`](./webchat/contracts/) (OpenAPI 3.1 & AsyncAPI 3.0).
  * An ninh đa tầng: Gitleaks (quét secret), Trivy (quét CVE container/dependencies), Nuclei (quét DAST endpoint).
  * Kiểm thử hợp đồng tự động: Schemathesis (OpenAPI property fuzzing) & Newman (Postman E2E collections).
  * Công cụ sinh unit test tự động: `webchat/tools/testgen/`.
  * Đường ống CI/CD tự động trên GitHub Actions: [`.github/workflows/webchat-checks.yml`](./.github/workflows/webchat-checks.yml).

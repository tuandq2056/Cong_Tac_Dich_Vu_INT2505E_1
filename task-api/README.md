## Khó khăn

### 1. Xung đột URI (`id`) giữa URL Path và Request Body trong `PUT`
* **Vấn đề :** 
  - `PUT /books/{book_id}` đã định danh rõ cuốn sách cần cập nhật qua URL. Tuy nhiên, schema `Book` dùng chung lại chứa cả trường `id`. 
    => Xung đột dữ liệu, nên lấy thằng nào?
* **Quyết định:** 
  - lấy trên url
  - server swagger bỏ qua trường `id` trong body và luôn gán ID theo URL. ( vì sao cần giữ lại ? : để dành cho post)
  - đặc tả: `id` là `readOnly: true` (hoặc loại bỏ khỏi payload cập nhật) để client không can thiệp vào primary key của resource.

### 2.  Không có cái thứ 2 ạ 

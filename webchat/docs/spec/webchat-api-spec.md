> Nguồn: `WebChat-API-Spec.docx`, phiên bản 1.0.0, 20/11/2026. Bản Markdown này giữ nguyên nội dung;
> file DOCX gốc là nguồn tham chiếu. Hai tệp `openapi.yaml` và `asyncapi.yaml` được nhắc trong tài liệu
> nhưng **chưa có trong thư mục nguồn** — xem `contracts/README.md`.

*PHIÊN BẢN 1.0.0     •     20 THÁNG 11 NĂM 2026*

# Đặc tả API WebChat

**Từ lời mời kết bạn đến tin nhắn được lưu, phát trực tiếp và đọc lại.**

Hợp đồng đề xuất cho dự án FastAPI và giao diện React/TypeScript, dựa trên bảng tính năng trong “Kế hoạch A+ API.docx”. Nhóm có thể dùng tài liệu này để triển khai từng dịch vụ, ghép frontend và thống nhất tiêu chí nghiệm thu.

| Thành phần | Phụ trách | Dữ liệu và giao diện chính |
|---|---|---|
| Identity | Tuân | Tài khoản, username, token và tra cứu người dùng. |
| Social | Nghĩa | Lời mời, quan hệ bạn bè, hội thoại, thành viên và quyền truy cập. |
| Chat | Long | Nội dung tin, tệp, thứ tự tin, mốc đọc và kết quả tóm tắt theo yêu cầu. |
| Web frontend | Lâm | Luồng màn hình, WebSocket, hợp nhất tin sau kết nối lại và phát giọng nói. |

### Tra cứu theo công việc

Luồng ví dụ     ·     Quy ước chung     ·     Tài khoản     ·     Google

Bạn bè     ·     Hội thoại     ·     Tệp và audio     ·     Lịch sử và tìm kiếm

Mốc đọc và tóm tắt     ·     Quyền nội bộ     ·     WebSocket     ·     Kết nối lại

Text-to-Speech     ·     Dữ liệu     ·     Nghiệm thu     ·     Giới hạn và hiệu năng

### Hai tệp kỹ thuật đi kèm

> Các đường dẫn, tham số, nội dung gửi và phản hồi HTTP nằm trong openapi.yaml

> Các khung JSON trên WebSocket và chiều gửi nhận nằm trong asyncapi.yaml

> Giữ hai tệp YAML cùng thư mục. WebSocket dùng chung cấu trúc Message và TextContent với REST.

## Từ kết bạn đến đọc lại tin

**An tìm Bình, hai người mở chat riêng và tiếp tục được cuộc trò chuyện sau khi tải lại trang.**

| Bước | Yêu cầu hoặc sự kiện | Kết quả cần thấy |
|---|---|---|
| 1 · Đăng nhập | An và Bình đăng ký rồi gọi POST /auth/login. | Mỗi người nhận một access_token và hồ sơ PublicUser của riêng mình. |
| 2 · Tìm bạn | An gọi GET /users/by-username/binh và POST /friend-requests với recipient_id của Bình. | An giữ ID lời mời. Bình thấy cùng ID khi liệt kê lời mời đến. |
| 3 · Chấp nhận | Bình PATCH lời mời với status=accepted. | Cả hai thấy nhau trong GET /friends ngay sau khi thành công. |
| 4 · Mở chat | Mỗi người PUT /conversations/direct/{friend_id} với ID của người kia. | Cùng một conversation_id, kể cả khi hai yêu cầu đồng thời. |
| 5 · Vào phòng | Mỗi trình duyệt xác thực WebSocket rồi gửi conversation.subscribe với ID vừa nhận. | Chat kiểm tra quyền thành viên qua Social và xác nhận đăng ký. |
| 6 · Gửi tin | Bình gửi message.send với client_message_id và nội dung text. | Sau commit, Bình nhận message.ack. An nhận message.created chứa cùng message.id. |
| 7 · Đọc lại | An tải lại trang, mở cùng hội thoại rồi GET /conversations/{conversation_id}/messages. | Tin đã lưu vẫn còn. Khi thật sự đọc hết tới seq đó, An cập nhật read-state. |

> Các đường dẫn REST rút gọn trong bảng dùng tiền tố /api/v1.

### Khi An tạo nhóm với Bình và Chi

An chọn hai người đã có trong danh sách bạn và đặt tên “Nhóm đồ án”. Social lưu nhóm cùng ba thành viên trong một giao dịch. Bình và Chi thấy nhóm từ GET /conversations. Cả ba dùng cùng luồng đăng ký WebSocket, gửi tệp và xem lịch sử như trong chat riêng.

## Quy ước tích hợp

**Giao diện công khai dùng /api/v1 qua HTTPS và /ws/v1/chat qua WSS. Hai API /internal/v1 chỉ phục vụ giao tiếp giữa các dịch vụ.**

| Thành phần hợp đồng | Quy ước |
|---|---|
| Xác thực | Sau khi đăng nhập, gửi Authorization: Bearer <access_token>. Token có aud=webchat, sub là UUID người dùng, username và exp. Mỗi dịch vụ kiểm tra chữ ký, issuer, audience và hạn trước khi dùng. |
| Định dạng | JSON UTF-8 và tên trường snake_case. Upload dùng multipart/form-data, download trả byte với Content-Type thực. ID là UUID. Ngày giờ là RFC 3339 UTC, ví dụ 2026-11-20T08:15:00Z. |
| Danh sách Social | limit mặc định 30, từ 1 đến 100. Gửi lại next_cursor dưới tên cursor với cùng đường dẫn, người dùng và bộ lọc. next_cursor=null khi hết. Danh sách rỗng vẫn trả 200. |
| Danh sách tin | seq tăng theo thứ tự commit trong một hội thoại. Dùng số nguyên dương đến 2⁵³−1. Giá trị 0 dành cho mốc ban đầu. before_seq và after_seq là cận mở. |
| Lỗi chung | 401 UNAUTHENTICATED cho token không hợp lệ. 422 VALIDATION_ERROR cho đầu vào sai. Chat trả 503 SOCIAL_UNAVAILABLE khi không kiểm tra được quyền, hoặc CHAT_UNAVAILABLE khi kho dữ liệu gặp lỗi. |

### Ví dụ phản hồi khi username bị trùng

```json
{
  "request_id": "55000000-0000-4000-8000-000000000011",
  "error": {
    "code": "USERNAME_TAKEN",
    "message": "Username đã được sử dụng."
  }
}
```

Client xử lý theo error.code. error.fields có thể chỉ rõ từng field và reason. request_id của phản hồi HTTP do dịch vụ cấp để tra nhật ký. Trên WebSocket, request_id do client tạo để ghép lệnh với kết quả.

> Định dạng của hợp đồng REST theo OpenAPI Specification 3.1.1

## Identity · tài khoản

**Username là tên duy nhất dùng khi đăng nhập và tìm bạn. Các dịch vụ tham chiếu tài khoản bằng UUID.**

```http
POST /api/v1/auth/register
```

Body Credentials có username và password. Username 3–32 ký tự ASCII gồm chữ, số và dấu gạch dưới. Identity lưu dạng chữ thường. Mật khẩu dài 8–128 điểm mã Unicode và giữ nguyên khoảng trắng. 201 trả PublicUser.

> Lỗi nghiệp vụ  409 USERNAME_TAKEN

```http
POST /api/v1/auth/login
```

Body Credentials giống đăng ký. 200 trả TokenResponse gồm access_token, token_type=Bearer, expires_in=3600 và user. Sai username hoặc mật khẩu đều nhận cùng một mã lỗi.

> Lỗi nghiệp vụ  401 INVALID_CREDENTIALS

```http
GET /api/v1/users/me
```

Gửi bearer token. 200 trả PublicUser của chính người gọi, dùng để đối chiếu sender.id trên giao diện.

```http
GET /api/v1/users/by-username/{username}
```

So khớp toàn bộ username, không phân biệt chữ hoa và thường. 200 trả PublicUser. Dùng id của kết quả làm recipient_id khi mời kết bạn.

> Lỗi nghiệp vụ  404 USER_NOT_FOUND

### Ví dụ tra cứu

```http
GET /api/v1/users/by-username/BINH
Authorization: Bearer <access_token>

200 OK
{"id": "b2000000-0000-4000-8000-000000000002", "username": "binh"}
```

Hai yêu cầu đăng ký “Binh” và “binh” đồng thời chỉ có thể tạo một tài khoản.

## Identity · đăng nhập Google

**Tính năng tùy chọn dùng OAuth 2.0 Authorization Code và OpenID Connect. Sau khi đăng nhập, frontend nhận cùng định dạng token WebChat như khi dùng mật khẩu.**

```http
GET /api/v1/auth/google/start
```

Trình duyệt điều hướng đến endpoint. Identity trả 302 với Location trỏ tới Google và Set-Cookie cho wc_google_flow. Cookie có HttpOnly, Secure, SameSite=Lax, Path=/api/v1/auth/google và thời hạn 300 giây.

> Lỗi nghiệp vụ  501 GOOGLE_DISABLED

```http
POST /api/v1/auth/google/exchange
```

Frontend POST JSON {code, state} từ trang callback cùng cookie wc_google_flow. 200 trả TokenResponse và xóa cookie giao dịch. Khi tính năng chưa bật, cả hai endpoint trả 501.

> Lỗi nghiệp vụ  400 OAUTH_STATE_INVALID   ·   401 GOOGLE_CODE_INVALID   ·   501 GOOGLE_DISABLED   ·   503 GOOGLE_UNAVAILABLE

### Trình tự đổi mã

1.  Identity yêu cầu response_type=code và scope=openid, tạo state, nonce và PKCE S256. Verifier và trạng thái giao dịch nằm phía máy chủ. redirect_uri là URL /auth/google/callback cố định trên origin của web và phải được đăng ký với Google.

2.  Google chuyển trình duyệt về trang callback với code và state. Trang đọc hai giá trị, xóa chúng khỏi thanh địa chỉ sau khi lấy rồi gửi đến exchange. Khi người dùng hủy tại Google, trang kết thúc luồng và hiển thị lại lựa chọn đăng nhập.

3.  Identity kiểm tra cookie và state dùng một lần, thực hiện đổi mã với verifier và kiểm tra chữ ký, issuer, audience, exp, nonce của ID token.

4.  Identity tra cặp (iss đã chuẩn hóa, sub). Lần đầu tạo tài khoản với username g_ kèm 16 ký tự hex ngẫu nhiên, thử lại nếu trùng. Các lần sau dùng đúng user_id đó. Một địa chỉ email giống tài khoản cũ vẫn tạo danh tính riêng.

> Giao thức định danh của nhà cung cấp được mô tả trong Google OpenID Connect

## Social · bạn bè và lời mời

**Mỗi cặp người có nhiều nhất một lời mời đang chờ. Một lần chấp nhận tạo quan hệ bạn bè cho cả hai phía.**

```http
POST /api/v1/friend-requests
```

Body {recipient_id}. 201 trả FriendRequest mới, 200 trả lời mời pending cùng chiều đã có. Nếu tồn tại lời mời ngược chiều, 409 trả error.related_id để người nhận có thể mở lời mời đó.

> Lỗi nghiệp vụ  404 USER_NOT_FOUND   ·   409 ALREADY_FRIENDS / INCOMING_REQUEST_EXISTS   ·   422 SELF_INVITE   ·   503 IDENTITY_UNAVAILABLE

```http
GET /api/v1/friend-requests
```

Query direction=incoming|outgoing, status=pending|accepted|declined|cancelled, limit và cursor. Mặc định incoming + pending. 200 trả FriendRequestPage theo created_at, id giảm dần.

> Lỗi nghiệp vụ  422 INVALID_CURSOR

```http
PATCH /api/v1/friend-requests/{request_id}
```

Body {status}. Người nhận chấp nhận hoặc từ chối. Người gửi thu hồi. 200 trả FriendRequest sau xử lý. Quyết định cũ gửi lại bởi đúng người trả 200, kể cả nếu sau đó hai người đã xóa bạn. Hai quyết định khác nhau cạnh tranh chỉ có một lần chuyển từ pending.

> Lỗi nghiệp vụ  403 ACTION_FORBIDDEN   ·   404 REQUEST_NOT_FOUND   ·   409 REQUEST_CLOSED

```http
GET /api/v1/friends
```

Query limit và cursor. 200 trả UserPage theo username, id tăng dần. Hai phía thấy nhau sau khi lời mời chuyển thành accepted.

> Lỗi nghiệp vụ  422 INVALID_CURSOR

```http
DELETE /api/v1/friends/{friend_id}
```

Xóa quan hệ hai chiều. 204 có body rỗng, gửi lại cũng nhận 204. Lịch sử chat riêng và tư cách thành viên các nhóm chung vẫn truy cập được. Gửi thêm tin riêng cần kết bạn lại.

## Social · hội thoại và thành viên

**Một cặp người dùng có một chat riêng. Mỗi lần tạo nhóm hợp lệ sinh một hội thoại độc lập với các nhóm cùng tên.**

```http
PUT /api/v1/conversations/direct/{friend_id}
```

Người gọi và friend_id phải đang là bạn. 201 trả DirectConversation mới, 200 trả hội thoại cũ. Hai thứ tự A–B và B–A dùng cùng ID bền vững. peer luôn là người còn lại theo góc nhìn người gọi.

> Lỗi nghiệp vụ  403 FRIENDSHIP_REQUIRED   ·   422 SELF_CONVERSATION

```http
POST /api/v1/conversations/groups
```

Body {name, member_ids}. Tên 1–80 điểm mã, có ký tự hiển thị sau khi bỏ khoảng trắng hai đầu. Chọn 2–49 bạn khác nhau, người tạo tự tham gia. Bắt buộc header Idempotency-Key dạng UUID. 201 trả GroupConversation, thử lại hợp lệ trong 24 giờ trả 200.

> Lỗi nghiệp vụ  403 FRIENDSHIP_REQUIRED   ·   409 IDEMPOTENCY_CONFLICT   ·   422 INVALID_MEMBERS

```http
GET /api/v1/conversations
```

Query limit và cursor. 200 trả ConversationPage theo created_at, id giảm dần. Chat riêng chứa peer, nhóm chứa name, created_by và member_count.

> Lỗi nghiệp vụ  422 INVALID_CURSOR

```http
GET /api/v1/conversations/{conversation_id}
```

200 trả DirectConversation hoặc GroupConversation. Người ngoài và ID hội thoại không tồn tại cùng nhận 404.

> Lỗi nghiệp vụ  404 CONVERSATION_NOT_FOUND

```http
GET /api/v1/conversations/{conversation_id}/members
```

Query limit và cursor. 200 trả UserPage sắp theo username, id tăng dần, gồm cả người gọi. Hiển thị được danh sách của cả chat riêng và nhóm.

> Lỗi nghiệp vụ  404 CONVERSATION_NOT_FOUND   ·   422 INVALID_CURSOR

> Tạo nhóm là thao tác nguyên tử. Một mục sai điều kiện làm toàn bộ yêu cầu thất bại. Cùng Idempotency-Key và cùng tập thành viên theo thứ tự khác vẫn tương ứng với một lần tạo.

## Chat · tệp đính kèm và audio

**Trình duyệt tải byte qua HTTP, rồi gửi ID tệp qua WebSocket để tạo tin. Việc tải lên thành công mới tạo một tệp chờ gắn.**

```http
POST /api/v1/conversations/{conversation_id}/attachments
```

Body multipart gồm kind=audio|file và đúng một phần file có filename. Cần can_send. 201 trả Attachment gồm id, kind, file_name, media_type, byte_size và thêm duration_ms cho audio.

> Lỗi nghiệp vụ  403 FRIENDSHIP_REQUIRED   ·   404 CONVERSATION_NOT_FOUND   ·   413 UPLOAD_TOO_LARGE   ·   415 UNSUPPORTED_MEDIA_TYPE   ·   422 INVALID_ATTACHMENT

```http
GET /api/v1/conversations/{conversation_id}/attachments/{attachment_id}/content
```

Cần bearer token và can_read. 200 trả byte với Content-Type phù hợp và Cache-Control: private, no-store. Content-Disposition là inline cho audio hoặc attachment cho file. Tệp chờ chỉ người tải đọc được. Khi đã gắn vào tin, thành viên có quyền đọc được tải.

> Lỗi nghiệp vụ  404 CONVERSATION_NOT_FOUND / ATTACHMENT_NOT_FOUND

| Loại | Điều kiện đầu vào | Gắn vào tin |
|---|---|---|
| audio | 1 byte đến 10 MiB, tối đa 300 giây. WebM, Ogg, MP4, MPEG hoặc WAV. Chat xác định MIME và thời lượng. | Gửi content.type=audio và attachment_id. Máy chủ đối chiếu kind của tệp đã lưu. |
| file | 1 byte đến 25 MiB. Chat xác định MIME, dùng application/octet-stream nếu chưa nhận diện. | Gửi content.type=file và attachment_id. Mỗi tệp thuộc một người tải và một hội thoại. |

### Ví dụ sau khi tải một đoạn ghi âm

```json
{"id": "33000000-0000-4000-8000-000000000009", "kind": "audio", "file_name": "ghi-am.webm", "media_type": "audio/webm", "byte_size": 64000, "duration_ms": 4200}
```

Client chép id vào attachment_id của message.send. Tin đã commit chứa lại metadata tệp để người nhận phát hoặc tải. Tệp chờ hết hạn sau 24 giờ. Thử upload lần nữa tạo ID mới. Gửi lại cùng lần gửi tin đã lưu trả ACK của tin gốc.

## Chat · lịch sử và tìm kiếm

**Khi mở màn hình, lấy trang mới nhất. Khi người dùng lướt lên, dùng seq của mục cuối để lấy trang cũ hơn.**

```http
GET /api/v1/conversations/{conversation_id}/messages
```

Query limit, before_seq hoặc after_seq. through_seq chỉ đi cùng after_seq và phải ≥ after_seq. 200 trả {items: Message[], has_more}. Trang gần nhất và trang cũ xếp seq giảm dần. Trang bù tin sau mất kết nối xếp tăng dần.

> Lỗi nghiệp vụ  404 CONVERSATION_NOT_FOUND   ·   422 INVALID_RANGE

```http
GET /api/v1/conversations/{conversation_id}/messages/search
```

Query q bắt buộc, limit và before_seq tùy chọn. Tìm chuỗi con trong text của đúng hội thoại, bỏ khoảng trắng hai đầu q, chuẩn hóa NFC, không phân biệt hoa thường và có phân biệt dấu. q dài 1–200 điểm mã. 200 trả các tin khớp kèm sender, created_at, seq. Không khớp trả items rỗng.

> Lỗi nghiệp vụ  404 CONVERSATION_NOT_FOUND

### Ví dụ phân trang với limit=2

| Mục đích | Tham số sau đường dẫn /messages | Kết quả minh họa |
|---|---|---|
| Mở trang mới nhất | ?limit=2 | seq 45, 44. has_more=true. |
| Lướt lên | ?before_seq=44&limit=2 | seq 43, 42. Không lặp lại tin 44. |
| Bù tin 41–45 | ?after_seq=40&through_seq=45&limit=2 | seq 41, 42. Tiếp theo dùng after_seq=42 và giữ through_seq=45. |
| Tìm trong text | /search?q=báo%20cáo&limit=2 | Tin có “BÁO CÁO” cũng khớp. “bao cao” được xem là cụm khác. |

has_more chỉ xét tập kết quả của truy vấn đang dùng. Client sắp seq tăng dần trước khi hiển thị theo dòng thời gian. Tải trang hoặc tìm kiếm không tự đánh dấu đã đọc.

## Chat · mốc đọc và tóm tắt

**Bấm “Tóm tắt” lấy các tin text gần nhất mà chính người dùng chưa đọc trong hội thoại đang mở.**

```http
GET /api/v1/conversations/{conversation_id}/read-state
```

200 trả last_read_seq, latest_seq và unread_text_count. Mốc đọc khởi tạo bằng 0. Chat đếm tin text của người khác sau mốc này.

> Lỗi nghiệp vụ  404 CONVERSATION_NOT_FOUND

```http
PUT /api/v1/conversations/{conversation_id}/read-state
```

Body {through_seq}. 200 trả ReadState mới. Chat ghi max(mốc cũ, through_seq) nguyên tử. Gọi lại hoặc có hai tab cập nhật ngược thứ tự đều cho kết quả nhất quán.

> Lỗi nghiệp vụ  404 CONVERSATION_NOT_FOUND   ·   422 READ_AHEAD

```http
POST /api/v1/conversations/{conversation_id}/unread-summary
```

POST không có body. 200 trả UnreadSummary. Chat cố định mốc đọc và snapshot_seq, lọc text của người khác trong khoảng mở–đóng rồi lấy tối đa 100 tin mới nhất. Chỉ nội dung text được gửi tới LLM, theo seq tăng dần. Kết quả không tự dời mốc đọc.

> Lỗi nghiệp vụ  404 CONVERSATION_NOT_FOUND   ·   503 SUMMARY_UNAVAILABLE

### An đã đọc đến 40, hội thoại hiện ở 45

| seq | Người gửi và loại tin | Có đưa vào tóm tắt cho An? |
|---|---|---|
| 41 | Bình · text · “Mai nộp báo cáo lúc 9 giờ nhé.” | Có. |
| 42 | Bình · audio · đoạn ghi âm | Bỏ qua audio. |
| 43 | An · text · “Đã rõ.” | Bỏ qua tin do chính An gửi. |
| 44 | Bình · file · bao-cao.pdf | Bỏ qua tệp và tên tệp. |
| 45 | Bình · text · “Nhớ mang bản in.” | Có. Kết quả dùng 2 tin, theo thứ tự 41 rồi 45. |

Tin 46 đến trong khi LLM chạy thuộc lần tóm tắt tiếp theo. Nếu chỉ còn audio hoặc file, trả status=empty, summary=null và source_count=0 ngay tại Chat. omitted_count cho biết còn bao nhiêu tin text cũ hơn đã bị cắt bởi giới hạn 100.

## Kiểm tra quyền giữa các dịch vụ

**Social sở hữu danh sách thành viên. Chat hỏi Social bằng token dịch vụ trước khi cho đọc, nhận sự kiện, gửi tin hoặc tải tệp.**

```http
GET /internal/v1/users/{user_id}
```

Social gọi Identity bằng service JWT với sub=social, aud=identity-internal. 200 trả PublicUser, dùng để kiểm tra người nhận lời mời. Token có audience khác nhận 401.

> Lỗi nghiệp vụ  403 SERVICE_FORBIDDEN   ·   404 USER_NOT_FOUND

```http
GET /internal/v1/conversations/{conversation_id}/members/{user_id}/permissions
```

Chat gọi Social bằng service JWT với sub=chat, aud=social-internal. user_id được lấy từ token người dùng đã xác thực. 200 trả {can_read, can_send}. Người ngoài và hội thoại vắng mặt cùng trả 404.

> Lỗi nghiệp vụ  403 SERVICE_FORBIDDEN   ·   404 CONVERSATION_NOT_FOUND

| Tình huống | can_read | can_send | Ứng xử của Chat |
|---|---|---|---|
| Hai người còn là bạn | true | true | Đọc, đăng ký nhận tin, upload và gửi. |
| Đã xóa bạn trong chat riêng | true | false | Đọc tin và tệp cũ. Gửi mới trả FRIENDSHIP_REQUIRED. |
| Thành viên nhóm | true | true | Quyền trong nhóm độc lập với quan hệ bạn bè sau lúc tạo. |
| Người ngoài | 404 | 404 | Ẩn hội thoại. Từ chối lịch sử, tìm kiếm, tệp, tóm tắt và subscribe. |
| Social không phản hồi | — | — | Trả SOCIAL_UNAVAILABLE. Dừng xử lý yêu cầu, không ACK thành công. |

Ví dụ Bình gửi tin nhóm. Chat xác thực Bình, gọi Social kiểm tra can_send, rồi mới ghi tin và công việc phát trong cùng một giao dịch. Sau commit, Chat gửi ACK cho Bình và chuyển message.created tới các socket đã đăng ký của thành viên.

## WebSocket · phiên và sự kiện

**Mở wss://<host>/ws/v1/chat. Mỗi khung là một đối tượng JSON UTF-8 dạng text, tối đa 32 KiB.**

| Tên trên đường truyền | Chiều | Payload ngoài type và ý nghĩa |
|---|---|---|
| session.authenticate | Web → Chat | request_id, access_token. Là lệnh đầu tiên trong 5 giây. |
| session.ready | Chat → Web | request_id, session_id, user_id, expires_at. Phiên đã xác thực. |
| conversation.subscribe | Web → Chat | request_id, conversation_id. Yêu cầu đăng ký hội thoại. |
| conversation.subscribed | Chat → Web | request_id, conversation_id, latest_seq. Sẵn sàng nhận tin và đồng bộ đến mốc này. |
| conversation.unsubscribe | Web → Chat | request_id, conversation_id. Gỡ đăng ký trên riêng socket gửi lệnh. |
| conversation.unsubscribed | Chat → Web | request_id, conversation_id. Xác nhận cả khi socket chưa đăng ký. |
| message.send | Web → Chat | request_id, conversation_id, client_message_id, content. Cần subscribe và can_send. |
| message.ack | Chat → Web | request_id, message, replayed. Cùng request_id với message.send, chỉ xuất hiện sau commit. |
| message.created | Chat → Web | message. Phát cho các socket theo dõi hội thoại, kể cả socket gửi. Dùng message.id để gộp bản trùng. |
| error | Chat → Web | request_id hoặc null, code, message, retryable. Chi tiết từng mã ở phần xử lý lỗi. |

### Khung đầu tiên của trình duyệt

```json
{
  "type": "session.authenticate",
  "request_id": "55000000-0000-4000-8000-000000000011",
  "access_token": "example-access-token"
}
```

> Token đặt trong khung xác thực đầu tiên. Cách này dùng được với WebSocket gốc của trình duyệt và giữ token ngoài URL.

> Chiều send/receive trong tệp YAML được mô tả từ góc nhìn Chat Service theo AsyncAPI Specification 3.0.0

## WebSocket · gửi và xác nhận

**request_id ghép một lệnh với câu trả lời. client_message_id nhận diện một lần gửi tin, xuyên suốt cả khi đổi kết nối.**

### Bình gửi văn bản cho An

```json
{
  "type": "message.send",
  "request_id": "55000000-0000-4000-8000-000000000011",
  "conversation_id": "d4000000-0000-4000-8000-000000000004",
  "client_message_id": "44000000-0000-4000-8000-000000000010",
  "content": {
    "type": "text",
    "text": "Mai nộp báo cáo lúc 9 giờ nhé."
  }
}
```

### ACK mà Bình nhận sau khi ghi xong

```json
{
  "type": "message.ack",
  "request_id": "55000000-0000-4000-8000-000000000011",
  "replayed": false,
  "message": {
    "id": "11000000-0000-4000-8000-000000000007",
    "conversation_id": "d4000000-0000-4000-8000-000000000004",
    "seq": 41,
    "sender": {"id": "b2000000-0000-4000-8000-000000000002", "username": "binh"},
    "created_at": "2026-11-20T08:15:00Z",
    "client_message_id": "44000000-0000-4000-8000-000000000010",
    "content": {"type": "text", "text": "Mai nộp báo cáo lúc 9 giờ nhé."}
  }
}
```

An nhận message.created với cùng đối tượng message. Nếu ACK và sự kiện đều tới socket của Bình, giao diện chỉ hiện một tin. Đối với audio hoặc file, Bình thay content bằng một trong hai dạng dưới đây sau khi upload.

```json
{"type": "audio", "attachment_id": "33000000-0000-4000-8000-000000000009"}
{"type": "file", "attachment_id": "22000000-0000-4000-8000-000000000008"}
```

## Mất kết nối và xử lý lỗi

**Ví dụ An đã đồng bộ đến 40. Trong lúc An mất mạng, hội thoại có thêm các tin 41–45.**

1.  Khi mạng trở lại, xác thực socket mới rồi gửi conversation.subscribe. Bắt đầu đệm message.created ngay từ lúc gửi lệnh subscribe.

2.  Chat đăng ký socket trước khi chụp latest_seq. Nếu conversation.subscribed trả 45, tải GET /messages?after_seq=40&through_seq=45, tiếp tục theo seq cuối cho đến khi has_more=false.

3.  Hợp nhất trang đã bù và các khung đang đệm theo message.id, hiển thị theo seq. Cập nhật mốc đã đồng bộ khi đã nhận đủ khoảng. Mốc đồng bộ của thiết bị và mốc đã đọc của người dùng phục vụ hai việc riêng.

4.  Gửi lại các tin đang chờ ACK với client_message_id và nội dung cũ. Chat trả cùng Message với replayed=true nếu lần đầu đã commit. Nếu lần đầu chưa commit, Chat lưu một tin mới.

### Client xử lý lỗi trên socket

| Nhóm mã | Xử lý |
|---|---|
| INVALID_FRAME, VALIDATION_ERROR | Sửa envelope hoặc payload. request_id=null nếu Chat không đọc được UUID. |
| UNAUTHENTICATED, ALREADY_AUTHENTICATED | Token sai hoặc hết hạn dẫn đến đóng 4401. Nếu đã xác thực, giữ phiên và chuyển sang subscribe. |
| NOT_SUBSCRIBED, CONVERSATION_NOT_FOUND, FRIENDSHIP_REQUIRED | Đăng ký hội thoại nếu có quyền. Nếu đã xóa bạn, mở lịch sử cũ và cập nhật trạng thái nhập tin. |
| ATTACHMENT_NOT_FOUND, ATTACHMENT_KIND_MISMATCH, ATTACHMENT_IN_USE | Kiểm tra ID, người tải, hội thoại và kind. Tải lại nếu tệp chờ hết hạn hoặc đã dùng cho tin khác. |
| CLIENT_MESSAGE_ID_CONFLICT | Cùng khóa nhưng payload thay đổi. Chỉ cấp khóa mới khi người dùng thực sự gửi một tin mới. |
| SOCIAL_UNAVAILABLE, CHAT_UNAVAILABLE | retryable=true. Thử lại với thời gian chờ tăng dần và giữ nguyên client_message_id. |

> Mã đóng kết nối. 1000 khi kết thúc bình thường, 1003 khi gửi khung nhị phân, 1009 khi khung quá lớn, 4408 khi hết 5 giây chờ xác thực, 4401 khi xác thực không còn hợp lệ.

## Text-to-Speech trên trình duyệt

**Khi người dùng bật đọc thành tiếng, giao diện xử lý tin đến của người khác trong hội thoại đang mở.**

| Nguồn tin | Khi chế độ đang bật | Kết quả người dùng thấy |
|---|---|---|
| message.created · text | Lấy message.content.text, tạo SpeechSynthesisUtterance, xếp vào hàng đợi speechSynthesis. Ưu tiên ngôn ngữ vi-VN nếu có giọng phù hợp. | Nghe nguyên văn từng tin mới theo thứ tự hiển thị. |
| message.created · audio | Đọc content.attachment.id, tải byte từ đường dẫn /attachments/{attachment_id}/content với bearer token. Gắn Blob URL cho trình phát và gọi play(). | Nghe bản ghi gốc. Nếu trình duyệt yêu cầu thao tác, hiện nút Phát để tiếp tục. |
| message.created · file | Hiển thị tên, dung lượng và thao tác tải. | Người dùng chủ động tải tệp. |
| ACK, bản phát lặp, tin của chính mình, lịch sử và kết quả tìm kiếm | So sánh sender.id và ID tin đã xử lý. Chỉ xếp phát sự kiện mới đến từ người khác. Tin bù từ REST được hiển thị. | Mở lại phòng hoặc nhận phát lại cùng message.id vẫn chỉ đọc một lần cho sự kiện mới. |

### Bật, tắt và chuyển hội thoại

Công tắc lưu trên thiết bị. Khi bật, chỉ xếp hàng các tin mới đến sau thao tác bật. Khi tắt hoặc rời hội thoại, hủy hàng đợi đọc và dừng phát audio đang chạy. Phát lần lượt để các đoạn âm thanh không chồng lên nhau.

Nếu trình duyệt thiếu tổng hợp giọng nói, vẫn hiển thị nội dung text và cho phát audio bằng điều khiển của trình phát. Tệp âm thanh lấy qua API Chat có kiểm tra quyền như các tệp khác.

> Phần tổng hợp giọng nói phía trình duyệt dựa trên Web Speech API · Speech synthesis

## Dữ liệu trả về

**Tên kiểu trong bảng khớp với components.schemas của OpenAPI. Các trường bên dưới là bắt buộc, trừ trường được ghi rõ là tùy chọn.**

| Kiểu | Cấu trúc và cách đọc |
|---|---|
| PublicUser / TokenResponse | PublicUser có id, username chuẩn hóa. TokenResponse có access_token, token_type, expires_in tính theo giây và user. |
| FriendRequest | id, sender, recipient, status, created_at. sender và recipient đều là PublicUser. status thuộc pending, accepted, declined, cancelled. |
| Conversation | Chat riêng có id, type=direct, peer, created_at. Nhóm có id, type=group, name, created_by, member_count và created_at. |
| Các kiểu trang | UserPage, FriendRequestPage và ConversationPage có items và next_cursor (chuỗi hoặc null). MessagePage và TextSearchPage có items và has_more (boolean). |
| Attachment | id, kind, file_name, media_type, byte_size. Riêng kind=audio có duration_ms. Tệp gắn vào nội dung tin được trả đủ metadata. |
| Message | id, conversation_id, seq, sender, created_at, client_message_id, content. sender là PublicUser tại thời điểm gửi. content phân loại theo type. |
| Message.content | text có {type, text}. audio và file đã lưu có {type, attachment}. Lệnh message.send dùng attachment_id cho hai loại này. |
| ReadState / Permissions | ReadState có last_read_seq, latest_seq, unread_text_count. Permissions có hai trường boolean can_read, can_send. |
| UnreadSummary | status, summary, source_count, omitted_count, last_read_seq, snapshot_seq, source_from_seq, source_to_seq. Khi empty, summary và hai mốc nguồn là null, hai số đếm bằng 0. |
| ErrorResponse | request_id và error. error có code và message, có thể thêm fields [{field, reason}] hoặc related_id. |

### Ví dụ tóm tắt cho khoảng chưa đọc 41–45

```json
{"status": "ready", "summary": "Bình nhắc nộp báo cáo lúc 9 giờ và mang bản in.", "source_count": 2, "omitted_count": 0, "last_read_seq": 40, "snapshot_seq": 45, "source_from_seq": 41, "source_to_seq": 45}
```

## Kiểm thử và nghiệm thu

**Bốn tầng kiểm thử dùng cùng quy tắc quan sát được qua REST và WebSocket. Các ca bên dưới là tiêu chí cho giai đoạn triển khai.**

| Tầng | Ca tiêu biểu | Điều kiện đạt |
|---|---|---|
| Unit / Service | Chuẩn hóa username, chuyển trạng thái lời mời, xác định can_send, lọc tin trong khoảng chưa đọc. | Username khác hoa thường quy về một giá trị. Đầu vào [text của bạn, audio, text của tôi, file, text của bạn] đưa đúng hai text vào LLM. |
| Integration / Component | Chạy Social với kho dữ liệu thật của môi trường test, Chat kết nối Social và kho tệp. Mô phỏng lỗi trước commit, sau commit và LLM quá hạn. | Mở chat riêng đồng thời chỉ có một id. Lỗi trước commit không có ACK thành công. Gửi lại sau commit chỉ có một tin. LLM lỗi giữ nguyên mốc đọc. |
| Contract | Kiểm tra request và response với openapi.yaml, từng frame với asyncapi.yaml. Kiểm cả lỗi 401/403/404/409/422/503 và ranh giới liên dịch vụ. | Message trong lịch sử, ACK và message.created cùng schema. Không chấp nhận tin text thiếu text, audio thiếu attachment_id hoặc có đồng thời text và file. |
| E2E / System | Hai trình duyệt thực hiện đăng ký → kết bạn → chat riêng → ghi âm và gửi tệp → tải lại. Thêm người thứ ba để tạo nhóm, kiểm tra TTS và tóm tắt. | Thành viên thấy cùng ID tin và lịch sử sau tải lại. Người ngoài không đọc hoặc tải được. Sau xóa bạn, lịch sử riêng còn đọc được và gửi mới bị chặn. |

### Tình huống cần chạy riêng

Hai thiết bị.  Cùng tài khoản gửi read-state lần lượt 45 rồi 40. Kết quả cuối bằng 45. Ngắt mạng ngay sau gửi và phát lại cùng client_message_id. Kho tin và màn hình chỉ có một bản.

Tóm tắt.  Với 104 tin text đủ điều kiện xen kẽ audio, LLM nhận 100 text mới nhất theo thứ tự tăng. Đầu ra source_count=100, omitted_count=4. Khi chỉ có audio và file, LLM không được gọi.

Google tùy chọn.  Khi bật, đăng nhập Google hai lần bằng cùng sub nhận cùng user_id. State dùng lại nhận 400. Khi tắt, cả start và exchange trả 501.

## Giới hạn đề xuất và kiểm thử tải

**Kế hoạch nguồn nêu các chức năng và loại tải cần kiểm thử. Các giá trị dưới đây là thông số đề xuất cho phiên bản đầu.**

| Quyết định thiết kế | Giá trị trong hợp đồng v1 |
|---|---|
| Chat riêng và nhóm | Xóa bạn giữ lịch sử và chặn gửi riêng đến khi kết bạn lại. Nhóm có 3–50 người kể cả người tạo. Tạo nhóm hỗ trợ thử lại trong 24 giờ. |
| Phiên và dữ liệu | Token 3.600 giây. Mỗi trang mặc định 30 mục, tối đa 100. Text tối đa 4.000 điểm mã. Bản ghi âm tối đa 10 MiB / 300 giây, tệp khác 25 MiB. Tệp chờ có hiệu lực 24 giờ. |
| Giọng nói và tóm tắt | TTS chạy ở thiết bị. Tóm tắt đồng bộ tối đa 100 tin text chưa đọc gần nhất của người khác. Chỉ thao tác cập nhật read-state làm tiến mốc đọc. |
| Tìm kiếm và Google | Tìm username chính xác. Tìm trong text theo chuỗi con, có phân biệt dấu. Google đăng nhập qua luồng mã ủy quyền và chuẩn định danh OpenID Connect, có thể tắt. |

### Mục tiêu hiệu năng để nhóm nghiệm thu

Bộ dữ liệu đề xuất gồm 100 hội thoại, mỗi hội thoại 10.000 tin và một tập từ khóa cố định có cả từ phổ biến lẫn từ hiếm. Tăng tải trong 2 phút rồi giữ 10 phút. Ghi rõ CPU, RAM, phiên bản cơ sở dữ liệu và trạng thái cache khi báo kết quả.

| Tải thử | Mục tiêu đề xuất khi giữ tải |
|---|---|
| 200 WebSocket xác thực đồng thời, phân vào 20 nhóm, gửi tổng 20 tin text/giây | p95 từ message.send đến ACK ≤ 500 ms, p95 đến socket người nhận ≤ 800 ms. Không thiếu tin đã ACK khi đối chiếu lịch sử. |
| 20 yêu cầu lịch sử/giây, 30 tin/trang, lướt qua nhiều trang | p95 ≤ 300 ms. Không lặp ID ở hai trang liên tiếp trong cùng chiều phân trang. |
| 10 yêu cầu tìm kiếm/giây trên cùng bộ dữ liệu | p95 ≤ 600 ms. Kết quả đúng hội thoại. Tỷ lệ lỗi hệ thống ngoài dự kiến < 1% trong mỗi bài tải. |

> p95 là giá trị mà 95% số lần đo không vượt quá. Các ngưỡng này dành cho việc đo trên bản chạy của dự án.

const services = [
  {
    name: 'Identity',
    detail: 'Tài khoản, username, token và tra cứu người dùng.',
  },
  {
    name: 'Social',
    detail: 'Lời mời, bạn bè, hội thoại, thành viên và quyền truy cập.',
  },
  {
    name: 'Chat',
    detail: 'Tin nhắn, tệp, thứ tự tin, mốc đọc và tóm tắt.',
  },
]

export default function App() {
  return (
    <main className="shell">
      <header>
        <p className="eyebrow">SOA · WebChat</p>
        <h1>WebChat</h1>
        <p className="lead">
          Từ lời mời kết bạn đến tin nhắn được lưu, phát trực tiếp và đọc lại.
        </p>
      </header>

      <section aria-label="Services" className="cards">
        {services.map((service) => (
          <article key={service.name} className="card">
            <h2>{service.name}</h2>
            <p>{service.detail}</p>
          </article>
        ))}
      </section>

      <footer>
        <p>
          Khung giao diện của milestone M0. Luồng đăng nhập, bạn bè và chat được thêm ở M1–M5.
        </p>
      </footer>
    </main>
  )
}

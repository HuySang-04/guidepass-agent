# Hướng dẫn Agent Lên Lịch Trình GuidePass Trip Agent

Bài tập phỏng vấn vị trí Thực tập sinh Kỹ sư AI tại GuidePass (9/2026): một chatbot lập kế hoạch lịch trình theo giờ tại TP.HCM, có tính đến thời tiết theo giờ (tránh mưa/nắng nóng) và tình trạng giao thông phụ thuộc vào thời điểm khởi hành. Trò chuyện bằng tiếng Việt, nhận lại phản hồi bằng ngôn ngữ tự nhiên kèm theo một lịch trình JSON có cấu trúc.

## Phạm vi (Scope)

Được xây dựng bám sát **các yêu cầu bắt buộc (mục 4)** của đề bài, giữ cho hệ thống đơn giản nhất có thể nhưng vẫn đảm bảo tính chính xác. Các tính năng nâng cao (mục 5) cố ý **không** được triển khai — bao gồm: RAG/Qdrant, tối ưu hóa lộ trình TSP, streaming SSE, thời gian di chuyển theo từng phương tiện (xe máy/ô tô/đi bộ), giao diện bản đồ, chất lượng không khí/hoàng hôn/ngày lễ, bộ công cụ đánh giá tự động (eval harness), bộ đệm/fallback đa nhà cung cấp ngoài những gì được lưu ý bên dưới, phản hồi song ngữ, và tính năng giọng nói. Việc bổ sung bất kỳ tính năng nào trong số này chỉ mang tính chất cộng thêm, không phải là viết lại từ đầu, nếu còn thời gian sau khi hoàn thành phần cốt lõi bắt buộc.

Không sử dụng LangChain hay LangGraph — agent sử dụng vòng lặp gọi công cụ (tool-calling loop) phong cách OpenAI thuần túy (`app/llm.py`), dài khoảng 100 dòng. Đây là một lựa chọn có chủ ý: dễ giải thích từng dòng trong buổi phỏng vấn hơn là sử dụng các framework đồ thị (graph framework), và đề bài cũng nêu rõ rằng việc sử dụng framework là không bắt buộc.

## Công nghệ (Gói miễn phí, không yêu cầu thẻ tín dụng)

| Nhu cầu | Lựa chọn | Lý do |
|---|---|---|
| LLM | **Groq hoặc Ollama Cloud**, đều tương thích với OpenAI, model `gpt-oss:120b` / `openai/gpt-oss-120b` | Khóa miễn phí, không cần thẻ, gọi công cụ (tool-calling) tốt. Cả hai đã được kiểm thử đầu cuối và hoạt động tốt; việc chuyển đổi chỉ mất 3 dòng thay đổi trong tệp `.env` (xem `.env.example`), không cần sửa code. Ollama Cloud cũng là dòng model được đề xuất trong đề bài; một máy chủ Ollama chạy cục bộ (local) hoàn toàn hoạt động theo cách tương tự (base URL `http://localhost:11434/v1`). |
| Thời tiết | **Open-Meteo** | Xác suất mưa theo giờ + nhiệt độ cảm nhận (feels-like), miễn phí, không cần khóa API. |
| Địa điểm (điểm tham quan + nhà hàng) | **Overpass API** (OpenStreetMap) | Miễn phí, không cần khóa, dữ liệu POI thực tế kèm các thẻ (name, cuisine, opening_hours). Mọi điểm dừng trong lịch trình trả về đều bắt nguồn từ một `osm:type/id` từ đây. |
| Geocoding | **Nominatim**, kèm theo **cơ chế dự phòng tìm kiếm tên qua Overpass** | Xem phần "Các vấn đề thường gặp" bên dưới — Nominatim bị chặn DNS trên ít nhất một nhà mạng Việt Nam (VNPT), vì vậy cơ chế dự phòng cùng họ giúp ứng dụng tiếp tục hoạt động mà không cần thêm nhà cung cấp thứ hai. |
| Định tuyến / thời gian di chuyển | Máy chủ thử nghiệm **OSRM** + một heuristic giờ cao điểm/mưa được tài liệu hóa | OSRM cung cấp khoảng cách/thời gian di chuyển thực tế trên đường; tuy nhiên nó không có dữ liệu giao thông trực tiếp (live traffic), vì vậy `app/tools/travel.py` nhân với heuristic bên dưới (được lấy từ mã nguồn mẫu của đề bài). |

Đây là bộ công nghệ "0 đồng, không cần thẻ" được đề xuất trong đề bài. Không sử dụng RAG/Qdrant vì đó là tính năng nâng cao và nằm ngoài phạm vi ở đây.

## Quy tắc Thời tiết → Trong nhà / Ngoài trời (được tài liệu hóa theo đặc tả)

Trong `app/config.py`:
- `HOT_APPARENT_C = 35.0` — nhiệt độ cảm nhận $\ge 35\text{ }^\circ\text{C}$ $\rightarrow$ tránh hoạt động ngoài trời.
- `RAIN_PROB_AVOID_PCT = 50` — xác suất mưa $\ge 50\%$ $\rightarrow$ tránh hoạt động ngoài trời.

Cả hai đều xuất phát trực tiếp từ ví dụ trong đề bài (`Nắng gắt, cảm nhận 36–38 °C`, `Chiều mưa 80–85%` $\rightarrow$ bảo tàng trong nhà). System prompt hướng dẫn LLM ưu tiên các điểm dừng có `indoor: true` hoặc chọn khung giờ khác bất cứ khi nào đạt ngưỡng tại thời điểm dự kiến đến, đồng thời giải thích lý do trong phần `weather_note`.

## Heuristic Giao thông (được tài liệu hóa theo đặc tả)

`app/tools/travel.py` sử dụng chính xác hàm `travel_minutes()` được cung cấp trong đề bài:

```python
RUSH_HOURS = [(time(7, 0), time(9, 0)), (time(16, 30), time(19, 0))]
factor = 1.0
if rush hour: factor *= 1.6
if rain_mm_h >= 2.0: factor *= 1.3
adjusted = base_minutes_from_OSRM * factor
```

Hàm `get_travel_time` luôn trả về cả `base_minutes` (thời gian định tuyến thực tế từ OSRM) và `adjusted_minutes`, đồng thời gắn nhãn kết quả là `source: "osrm-demo(no live traffic)+rush/rain-heuristic"` để agent (và người đọc README) biết rằng đây là ước tính, không phải mức độ ùn tắc đo lường thực tế — đề bài yêu cầu rõ ràng phải công khai điều này thay vì trình bày như dữ liệu thời gian thực.

## Cách chạy ứng dụng

```bash
python -m venv .venv
.venv/Scripts/activate        # .venv/bin/activate trên macOS/Linux
pip install -r requirements.txt
cp .env.example .env          # thêm khóa Groq của bạn tại: https://console.groq.com/keys
uvicorn app.main:app --reload
```

Mở http://localhost:8000 để sử dụng giao diện chat tối giản, hoặc gọi API trực tiếp:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "demo1", "message": "Mình ở khách sạn gần chợ Bến Thành, thứ Bảy này rảnh từ 8h đến 20h. Thích lịch sử và đồ ăn đường phố, ngân sách khoảng 500k/người."}'
```

Gửi lại yêu cầu với cùng `session_id` để tiếp tục cuộc trò chuyện (các kịch bản 2–6 trong đề bài) — agent sẽ chỉnh sửa trực tiếp lịch trình hiện có thay vì lập kế hoạch lại toàn bộ ngày, sử dụng lịch trình đã lưu của phiên làm ngữ cảnh.

Đã được kiểm thử với Python 3.10 và 3.12; không sử dụng cú pháp chỉ dành riêng cho 3.11, mặc dù đề bài yêu cầu 3.11+ — dùng phiên bản nào cũng được.

## Dữ liệu thực tế vs. dữ liệu ước tính (Yêu cầu công khai bắt buộc)

- **Dữ liệu thực tế, từ API trực tiếp**: mọi địa điểm (tên, tọa độ, giờ mở cửa khi có thẻ, món ăn) đều đến từ Overpass/OpenStreetMap tại thời điểm yêu cầu — không có gì được mã hóa cứng (hardcoded) hay bịa đặt. Thời tiết là dự báo hàng giờ thực tế của Open-Meteo. Khoảng cách/thời gian định tuyến là mạng lưới đường thực tế của OSRM.
- **Dữ liệu ước tính, không đo lường trực tiếp**: `adjusted_minutes` (hệ số nhân giờ cao điểm/trời mưa ở trên) là một heuristic, không phải dữ liệu giao thông thời gian thực — máy chủ thử nghiệm miễn phí của OSRM không có dữ liệu đó. Agent được hướng dẫn nói rõ điều này bất cứ khi nào người dùng hỏi về thời gian di chuyển.
- **Không có dữ liệu giả lập (mock)**. Nếu một tìm kiếm không trả về địa điểm phù hợp (kịch bản 6: một quán phở mở cửa lúc 2 giờ sáng), agent được hướng dẫn trả lời trung thực thay vì tự bịa ra — điều này được thực thi cả trong system prompt lẫn cấu trúc (các điểm dừng chỉ có thể được tạo từ kết quả `search_places`, mỗi điểm mang theo nguồn gốc `osm:type/id` có thể truy xuất).

## Các vấn đề thường gặp / Hạn chế

- **Lỗi chặn DNS Nominatim trên một số nhà mạng.** Trong quá trình xây dựng, `nominatim.openstreetmap.org` trả về lỗi NXDOMAIN cụ thể từ trình phân giải DNS của một nhà mạng Việt Nam (VNPT), trong khi mọi máy chủ khác được sử dụng ở đây đều phân giải bình thường — đã xác nhận bằng lệnh `nslookup` đối với cả trình phân giải của nhà mạng và `1.1.1.1`. Hàm `geocode()` thử Nominatim trước và chuyển sang dự phòng tìm kiếm tên qua Overpass trong khung giới hạn (bounding box) của TP.HCM nếu bất kỳ yêu cầu nào thất bại, do đó ứng dụng vẫn hoạt động trên các mạng gặp sự cố này. Nếu bạn không ở trên mạng bị ảnh hưởng, Nominatim hoạt động bình thường và cơ chế dự phòng không bao giờ kích hoạt.
- **Máy chủ công cộng của Overpass hoạt động theo hình thức chia sẻ/sử dụng công bằng (fair-use)** và có thể trả về lỗi "server too busy" (406) hoặc hết thời gian chờ cổng (504) khi chịu tải lớn — quan sát trực tiếp trong quá trình kiểm thử. `_overpass_query()` thử lại một lần sau một khoảng dừng ngắn; lỗi lần thứ hai sẽ được chuyển đổi thành lỗi công cụ (tool error) cho LLM, và (theo system prompt) LLM phải báo cáo trung thực thay vì che đậy. Nếu đây trở thành vấn đề lớn, giải pháp là thêm nhà cung cấp thứ hai (Geoapify có gói miễn phí) phía sau cùng trợ giúp thử lại — cố ý chưa xây dựng lúc này vì đó là tính năng nâng cao.
- **Giới hạn tốc độ LLM gói miễn phí (Groq ~30 RPM) có thể bị chạm trong cuộc trò chuyện dài.** Một lịch trình cả ngày (geocode + thời tiết + 2 tìm kiếm rộng + một lần `get_travel_time` cho mỗi chặng + kiểm tra + phản hồi) dễ dàng đạt 15-20 lượt gọi LLM — mỗi lượt là một yêu cầu, do đó một loạt lượt hỏi liên tục trong cùng một phút (kiểm thử thủ công nặng, hoặc người dùng chỉnh sửa lại nhanh chóng) có thể vượt quá giới hạn RPM của gói miễn phí. Cơ chế tự động thử lại kèm thời gian chờ (retry-with-backoff) của SDK OpenAI hấp thụ các lỗi 429 thỉnh thoảng xảy ra; một chuỗi lỗi liên tục vẫn hiển thị dưới dạng thông báo `RateLimitError` rõ ràng thay vì bị sập (xem `app/main.py`). Nếu bạn gặp lỗi này khi thuyết trình/demo: hãy đợi ~60 giây, hoặc trỏ `.env` về Ollama cục bộ (không giới hạn RPM).
  **Đã xác nhận đầu cuối** trên cả Groq và Ollama Cloud trong quá trình phát triển — các lượt chạy kịch bản 1 hoàn chỉnh (nhật ký `guidepass.llm`, chạy theo từng vòng) hoàn thành chính xác: geocode $\rightarrow$ thời tiết $\rightarrow$ tìm kiếm rộng rồi chọn $\rightarrow$ `get_travel_time` theo từng chặng với `precipitation_mm` của thời tiết được truyền vào dưới dạng `rain_mm_h` $\rightarrow$ `validate_schedule` $\rightarrow$ lịch trình cuối cùng đúng cú pháp JSON được xây dựng hoàn toàn từ các địa điểm OSM thực tế.
- **Không phải mọi model đều gọi công cụ chính xác như yêu cầu.** `gpt-oss:120b` qua Ollama Cloud đôi khi: bỏ qua enum `category` và tự bịa ra các giá trị như `"museum"`/`"historic"` (tìm kiếm âm thầm chuyển về `"attraction"`, lãng phí lượt gọi mà không có phản hồi — đã khắc phục bằng cách làm cho `search_places` trả về lỗi rõ ràng cho danh mục không được nhận dạng); sử dụng tên trường khác cho các điểm dừng của `validate_schedule` (`start_time` thay vì `arrive`) — model tự sửa lỗi ngay khi thấy thông báo lỗi trả về, vì vậy giải pháp là làm cho thông báo lỗi nêu rõ các khóa bắt buộc chính xác; và đôi khi xuất ra JSON hợp lệ cuối cùng dưới dạng nội dung tin nhắn thông thường thay vì thực sự gọi `respond_with_itinerary`, mặc dù system prompt yêu cầu luôn gọi hàm đó. Hàm `app/llm.py::_try_parse_itinerary_json()` phát hiện trường hợp đó và khôi phục câu trả lời thay vì loại bỏ một phản hồi hoàn hảo — đây là điều mà một lượt chạy ít vòng hơn có thể bị mất. Việc lưu trữ model tương tự của Groq không cho thấy các vấn đề này trong quá trình kiểm thử; hãy coi đây là đặc tính của backend suy luận cụ thể, chứ không phải trọng số của model.
- **Việc phân tích cú pháp `opening_hours` mang tính chất cố gắng hết sức (best-effort).** Cú pháp `opening_hours` của OSM là một ngữ pháp nhỏ (phạm vi ngày, "PH off", chú thích...); phân tích cú pháp đầy đủ là một dự án riêng biệt, và bản thân đề bài cũng lưu ý rằng các địa điểm nhỏ thường thiếu dữ liệu này. Hàm `app/tools/places.py::is_open()` xử lý trường hợp phổ biến `[Days ]HH:MM-HH:MM` và trả về `None` ("không rõ, đừng chặn lại") đối với bất kỳ cấu trúc phức tạp nào — `validate_schedule` chỉ gắn cờ một điểm dừng khi nó có thể xác nhận chắc chắn rằng điểm đó đóng cửa.
- **Trạng thái phiên (Session state) được lưu trong bộ nhớ RAM** (`app/session.py`), được định danh bằng `session_id`, và sẽ bị mất khi khởi động lại ứng dụng. Phù hợp cho bản demo đơn tiến trình (single-process); hãy thay thế từ điển bằng Redis/SQLite nếu cần duy trì trạng thái sau khi khởi động lại.

## Các kịch bản kiểm thử thủ công (từ đề bài, mục 3)

Chạy các kịch bản này theo thứ tự với cùng một `session_id`:

1. "Mình ở khách sạn gần chợ Bến Thành, thứ Bảy này rảnh từ 8h đến 20h. Thích lịch sử và đồ ăn đường phố, ngân sách khoảng 500k/người."
2. "Dự báo chiều mưa to, đổi giúp mình phần buổi chiều."
3. "Bữa trưa đổi sang quán chay gần đó nha."
4. "À mình đi với ông bà 70 tuổi, hạn chế đi bộ."
5. "18h tối nay đi từ Quận 1 lên Landmark 81 mất bao lâu? Đi lúc 20h thì sao?"
6. "Cho mình quán phở mở cửa lúc 2h sáng ở Quận 5."

## 📺 Video Demo

Mời bạn xem video ngắn minh họa luồng hoạt động của agent (giao diện chat, xử lý thời tiết, cập nhật lịch trình theo `session_id`):

<p align="center">
  <a href="https://drive.google.com/file/d/1UFeZF4Fr-VNiA_ut8oeWgdPZ_xfTFeGE/view?usp=sharing">
    <img src="https://img.shields.io/badge/▶_Xem_Video_Demo_Google_Drive-FF0000?style=for-the-badge&logo=googledrive&logoColor=white" alt="Xem Demo Google Drive"/>
  </a>
</p>

---
*Phát triển cho GuidePass Internship Assessment - 2026.*
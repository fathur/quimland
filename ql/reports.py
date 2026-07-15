"""Fund closing-report generation: Markdown draft, then PDF from that draft.

Two explicit steps, both synchronous (no async task queue yet):
  1. generate_fund_report_draft() — creates a Report row with dummy Markdown
     content, status DRAFT. The user edits `content` in the admin.
  2. generate_report_pdf() — converts the current `content` to HTML and
     renders it into the themed PDF, status DONE.
"""
from django.utils import timezone

from .utils import render_report_markdown


def _dummy_report_markdown(fund):
    """Placeholder Markdown body. No DB queries — figures are all dummy."""
    return f"""# Pendahuluan

Dokumen ini disusun sebagai laporan resmi atas penutupan dana
**{fund.name}**. Laporan ini bertujuan untuk memberikan gambaran
menyeluruh mengenai pengelolaan dana selama periode berjalan, mencakup
ringkasan penerimaan, pengeluaran, serta status akhir saldo pada saat
dana dinyatakan ditutup.

Penyusunan laporan ini merupakan bagian dari tata kelola keuangan yang
transparan dan akuntabel, sehingga seluruh pihak terkait dapat memperoleh
informasi yang jelas mengenai penggunaan dana yang telah dikumpulkan,
serta dapat menilai kesesuaian antara rencana awal penggalangan dana
dengan realisasi yang telah dilaksanakan.

## Latar Belakang

Dana ini dibentuk untuk menghimpun kontribusi warga guna membiayai
kegiatan atau kebutuhan bersama yang telah disepakati sebelumnya. Selama
masa aktifnya, dana dikelola oleh pengurus yang bertanggung jawab atas
pencatatan setiap penerimaan dan pengeluaran, serta memastikan
penggunaan dana sesuai dengan tujuan awal pembentukannya.

Setelah seluruh rangkaian kegiatan atau kebutuhan yang menjadi tujuan
pembentukan dana selesai dilaksanakan, dana kemudian dinyatakan ditutup.
Penutupan ini menandai berakhirnya siklus pengelolaan dan menjadi dasar
bagi disusunnya laporan pertanggungjawaban ini.

## Tujuan Penyusunan Laporan

Laporan ini disusun dengan tujuan untuk:

1. Memberikan informasi yang akurat mengenai posisi keuangan dana pada
   saat penutupan.
2. Menjadi bahan pertanggungjawaban pengurus kepada seluruh kontributor
   dan pihak yang berkepentingan.
3. Menjadi arsip dokumentasi yang dapat dijadikan rujukan di kemudian
   hari apabila diperlukan.

## Ruang Lingkup

Ruang lingkup laporan ini mencakup seluruh transaksi yang tercatat sejak
dana dibentuk hingga dinyatakan ditutup, termasuk namun tidak terbatas
pada penerimaan kontribusi, realisasi pengeluaran per kategori, serta
rekapitulasi saldo akhir. Laporan ini tidak mencakup proyeksi atau
rencana penggunaan dana di luar periode pengelolaan yang telah berjalan.

> Catatan: bagian ini berisi konten sementara (dummy) untuk keperluan
> pratinjau tata letak. Narasi pendahuluan akan disesuaikan dengan data
> dana aktual pada versi mendatang.

# Laporan Keuangan

Bagian ini menyajikan gambaran arus kas dana selama periode pengelolaan,
mulai dari total dana yang berhasil dihimpun, realisasi pengeluaran per
kategori, hingga rekapitulasi saldo akhir yang tersisa pada saat dana
dinyatakan ditutup.

## Ringkasan Umum

| Kategori | Jumlah |
| --- | ---: |
| Total Dana Terkumpul | Rp 0 |
| Total Realisasi Pengeluaran | Rp 0 |
| Sisa Saldo Sebelum Penutupan | Rp 0 |
| **Saldo Akhir** | **Rp 0** |

## Rincian Penerimaan per Bulan

Tabel berikut merinci penerimaan kontribusi yang tercatat pada setiap
periode bulanan selama dana ini aktif dikelola.

| Periode | Jumlah Kontributor | Total Penerimaan |
| --- | ---: | ---: |
| Bulan 1 | 0 | Rp 0 |
| Bulan 2 | 0 | Rp 0 |
| Bulan 3 | 0 | Rp 0 |
| Bulan 4 | 0 | Rp 0 |
| Bulan 5 | 0 | Rp 0 |
| Bulan 6 | 0 | Rp 0 |
| **Total** | **0** | **Rp 0** |

## Rincian Pengeluaran per Kategori

Realisasi pengeluaran dikelompokkan berdasarkan kategori penggunaan
untuk memudahkan telaah kesesuaian antara pengeluaran dengan tujuan awal
pembentukan dana.

| Kategori Pengeluaran | Jumlah Transaksi | Total Pengeluaran |
| --- | ---: | ---: |
| Kebutuhan Operasional | 0 | Rp 0 |
| Bahan & Perlengkapan | 0 | Rp 0 |
| Jasa & Tenaga Kerja | 0 | Rp 0 |
| Administrasi | 0 | Rp 0 |
| Lain-lain | 0 | Rp 0 |
| **Total** | **0** | **Rp 0** |

Seluruh transaksi yang tercatat telah melalui proses verifikasi oleh
pengurus sebelum dibukukan. Bukti pendukung untuk setiap transaksi,
apabila tersedia, disimpan secara terpisah sebagai lampiran dan dapat
diakses melalui sistem pencatatan internal.

> Catatan: seluruh nominal dan rincian pada tabel-tabel di atas adalah
> data contoh (placeholder) dan belum diambil dari basis data transaksi.
> Nilai aktual akan ditampilkan setelah proses perhitungan data
> terintegrasi.

# Kesimpulan

Berdasarkan uraian pada bagian sebelumnya, pengelolaan dana
**{fund.name}** telah dilaksanakan sesuai dengan tujuan penggalangan
dana yang telah disepakati bersama, dan dana ini resmi dinyatakan
ditutup pada tanggal laporan ini diterbitkan.

Seluruh penerimaan dan pengeluaran telah dicatat dan
dipertanggungjawabkan sesuai dengan prinsip transparansi dan
akuntabilitas yang menjadi acuan dalam pengelolaan dana bersama. Tidak
terdapat catatan khusus yang memerlukan tindak lanjut lebih jauh terkait
pengelolaan dana ini.

## Rekomendasi

Untuk pengelolaan dana serupa di masa mendatang, disarankan agar proses
pencatatan dilakukan secara berkala dan konsisten, serta laporan
pertanggungjawaban disusun segera setelah dana dinyatakan ditutup guna
menjaga relevansi dan akurasi informasi yang disajikan.

## Penutup

Demikian laporan ini disusun sebagai bentuk pertanggungjawaban atas
pengelolaan dana **{fund.name}**. Laporan ini diharapkan dapat menjadi
dokumentasi resmi dan bahan pertanggungjawaban kepada seluruh pihak yang
berkepentingan.
"""


def generate_fund_report_draft(fund, user):
    """Create a Report row with dummy Markdown content, status DRAFT."""
    now = timezone.now()
    from .models import Report

    report = Report.objects.create(
        fund=fund,
        title=f'Laporan Keuangan — {fund.name} ({now:%d %b %Y})',
        creator=user,
        status=Report.Status.PROCESSING,
    )
    report.content = _dummy_report_markdown(fund)
    report.status = Report.Status.DRAFT
    report.save(update_fields=['content', 'status', 'updated_at'])
    return report


def generate_report_pdf(report):
    """Render the report's current Markdown content into the themed PDF."""
    import weasyprint
    from django.core.files.base import ContentFile
    from django.template.loader import render_to_string

    generated_at = timezone.now()
    content_html = render_report_markdown(report.content)
    html = render_to_string('admin/ql/fund/report_pdf.html', {
        'fund': report.fund,
        'content_html': content_html,
        'generated_at': generated_at,
        'generated_by': report.creator,
    })
    pdf_bytes = weasyprint.HTML(string=html).write_pdf()

    filename = f'laporan-{report.fund_id}-{generated_at:%Y%m%d-%H%M%S}.pdf'
    report.file.save(filename, ContentFile(pdf_bytes), save=False)
    report.status = report.Status.DONE
    report.completed_at = generated_at
    report.save(update_fields=['file', 'status', 'completed_at', 'updated_at'])
    return report

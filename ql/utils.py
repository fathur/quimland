def fmt_rupiah(amount):
    formatted = f'{amount:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'Rp {formatted}'

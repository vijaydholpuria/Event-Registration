import qrcode

def generate_qr(data):

    path="static/uploads/"+data+".png"

    img=qrcode.make(data)

    img.save(path)

    return path
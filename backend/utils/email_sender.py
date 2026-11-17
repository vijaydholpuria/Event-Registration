import random

def send_otp(email):

    otp=str(random.randint(100000,999999))

    print("OTP sent to",email,"OTP:",otp)

    return otp
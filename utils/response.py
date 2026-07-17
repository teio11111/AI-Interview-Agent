from flask import jsonify


def success(data=None, message='success', code=200):
    """统一成功响应"""
    return jsonify({
        'code': code,
        'message': message,
        'data': data
    }), code


def error(message='error', code=500, data=None):
    """统一失败响应"""
    return jsonify({
        'code': code,
        'message': message,
        'data': data
    }), code


def created(data=None, message='created'):
    """创建成功响应（201）"""
    return success(data=data, message=message, code=201)
